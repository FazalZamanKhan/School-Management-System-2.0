import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { installSessionWatch, onSessionExpired } from "./sessionWatch";

const AuthContext = createContext(null);

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);

  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }

  return null;
}

async function readJson(response, fallback) {
  const text = await response.text();

  if (!text) {
    throw new Error(
      `${fallback} The server returned an empty response ` +
        `(HTTP ${response.status}). Check that the Django API is ` +
        "running and reachable."
    );
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(
      `${fallback} The server returned a non-JSON response ` +
        `(HTTP ${response.status}). Check the browser's Network ` +
        "tab for details."
    );
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchMe = useCallback(() => {
    return fetch("/api/auth/me/", {
      credentials: "include",
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("not authenticated");
        }

        return readJson(response, "Could not load account.");
      })
      .then((data) => {
        setUser(data);
        setError("");
      })
      .catch(() => {
        setUser(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchMe();
  }, [fetchMe]);

  useEffect(() => {
    installSessionWatch();

    return onSessionExpired(() => {
      setUser(null);
      setLoading(false);
      setError("Your session has expired. Please sign in again.");
    });
  }, []);

  const login = useCallback(
    async (username, password, schoolCode = "", otp = "") => {
      setError("");

      await fetch("/api/auth/csrf/", {
        method: "GET",
        credentials: "include",
      });

      const response = await fetch("/api/auth/login/", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
        body: JSON.stringify({
          username,
          password,
          school_code: schoolCode,
          ...(otp ? { otp } : {}),
        }),
      });

      let data;
      try {
        data = await readJson(
          response,
          "Unable to sign in."
        );
      } catch {
        // readJson threw (empty/non-JSON response) — surface a clear message
        const err = new Error(
          "Unable to sign in. The server returned an unexpected response. " +
            "Check that the backend API is running and reachable."
        );
        throw err;
      }

      if (!response.ok) {
        let message = "Unable to sign in.";

        if (data.detail) {
          message = Array.isArray(data.detail)
            ? data.detail.join(", ")
            : data.detail;
        } else if (data.non_field_errors) {
          message = Array.isArray(data.non_field_errors)
            ? data.non_field_errors.join(", ")
            : data.non_field_errors;
        } else if (data.code) {
          // Handle DRF numeric error codes gracefully
          message = String(data.code);
        }

        const err = new Error(message);

        if (data.otp_required) {
          err.otpRequired = true;
        }

        throw err;
      }

      setUser(data);
      return data;
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await fetch("/api/auth/logout/", {
        method: "POST",
        credentials: "include",
        headers: {
          "X-CSRFToken": getCookie("csrftoken") || "",
        },
      });
    } finally {
      setUser(null);
    }
  }, []);

  const hasRole = useCallback(
    (roles) => {
      if (!user) return false;

      const userRoles = new Set();

      for (const membership of user.memberships || []) {
        for (const assignment of membership.roles || []) {
          userRoles.add(assignment.role);
        }
      }

      if (user.is_superuser) return true;

      return roles.some((role) => userRoles.has(role));
    },
    [user]
  );

  const hasPermission = useCallback(
    (permission) => {
      if (!user) return false;
      if (user.is_superuser) return true;
      
      // Check user's effective permissions
      const permissions = new Set();

      // If user has explicit permissions in the data, use them
      if (user.permissions) {
        for (const p of user.permissions) {
          permissions.add(p);
        }
      }
      
      // Fallback to role-based check
      const userRoles = new Set();
      for (const membership of user.memberships || []) {
        for (const assignment of membership.roles || []) {
          userRoles.add(assignment.role);
        }
      }
      
      // Superuser has all permissions
      if (user.is_superuser) return true;
      
      // Admin roles have most permissions
      const adminRoles = ["super_admin", "admin", "principal", "vice_principal", "campus_admin", "academic"];
      const hasAdminRole = adminRoles.some(r => userRoles.has(r));
      
      // For now, fall back to role-based for common admin permissions
      if (hasAdminRole) return true;
      
      return permissions.has(permission);
    },
    [user]
  );

  const value = useMemo(
    () => ({
      user,
      loading,
      error,
      login,
      logout,
      hasRole,
      hasPermission,
      refresh: fetchMe,
    }),
    [user, loading, error, login, logout, hasRole, hasPermission, fetchMe]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- hook must live beside the provider
export function useAuth() {
  const context = useContext(AuthContext);

  if (context === null) {
    throw new Error(
      "useAuth must be used within an AuthProvider."
    );
  }

  return context;
}
