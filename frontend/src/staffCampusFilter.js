export function matchesStaffCampus(member, campus) {
  return !campus || [member.primary_campus, member.campus].some(
    (value) => value != null && String(value) === String(campus),
  );
}
