import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from apps.schools.models import School, Campus
from apps.accounts.models import InstitutionMembership, RoleAssignment, Role

User = get_user_model()

class CampusDeleteTest(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='Test School', code='TEST001')
        self.campus = Campus.objects.create(school=self.school, name='Test Campus')
        
        self.user = User.objects.create_user(username='testadmin', password='testpass', email='test@test.com')
        from apps.accounts.models import InstitutionMembership, RoleAssignment, Role
        membership = InstitutionMembership.objects.create(user=self.user, institution=self.school, status='active')
        RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
        
        self.client = Client()
        self.client.login(username='testadmin', password='testpass')
        
    def test_delete_campus(self):
        # Test direct model delete
        print('Testing direct campus.delete()...')
        campus = Campus.objects.create(school=self.school, name='Direct Delete Campus')
        try:
            campus.delete()
            print('SUCCESS: Direct campus.delete() worked')
        except Exception as e:
            import traceback
            print(f'ERROR in direct delete: {type(e).__name__}: {e}')
            import traceback
            traceback.print_exc()
        
        # Test API delete
        print('\nTesting API campus delete...')
        campus = Campus.objects.create(school=self.school, name='API Delete Campus')
        
        # Get CSRF token
        response = self.client.get('/api/auth/csrf/', HTTP_REFERER='https://perfect-foundation-sms.vercel.app/')
        csrf_token = response.cookies.get('csrftoken').value if response.cookies.get('csrftoken') else None
        
        response = self.client.delete(
            f'/api/schools/campuses/{campus.id}/',
            HTTP_X_CSRFTOKEN=csrf_token,
            HTTP_REFERER='https://perfect-foundation-sms.vercel.app/'
        )
        print(f'API Delete Status: {response.status_code}')
        print(f'API Delete Response: {response.content}')
        
        # Verify deletion
        if response.status_code in [200, 204]:
            print('SUCCESS: Campus deleted via API')
        else:
            print('FAILED: Campus not deleted')

if __name__ == '__main__':
    import django
    from django.test.utils import setup_test_environment, setup_databases
    setup_test_environment()
    db_cfg = setup_databases(verbosity=1, interactive=False)
    
    test = CampusDeleteTest('test_delete_campus')
    test.setUp()
    test.test_delete_campus()