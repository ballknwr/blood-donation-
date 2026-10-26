import os
import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from app import create_app


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only', 'DATABASE': self.tmp.name+'/test.sqlite'})
        self.recipient = self.account('Recipient', 'recipient@example.test')
        self.donor = self.account('Donor', 'donor@example.test')
        self.other = self.account('Other', 'other@example.test')

    def tearDown(self):
        self.tmp.cleanup()

    def account(self, name, email):
        client=self.app.test_client()
        self.assertEqual(self.post(client,'register',{'name':name,'email':email,'password':'test-password-123'}).status_code,201)
        return client

    def post(self,client,path,body):
        csrf=client.get('/api/session').json['csrf']
        return client.post('/api/'+path,json=body,headers={'X-CSRF-Token':csrf})

    def profile(self,client=None,**extra):
        payload={'blood_group':'O+','city':'Bengaluru','lat':12.97,'lon':77.59,'phone':'+919000000001',
                 'age':25,'weight':65,'available':True,'whatsapp_consent':True,'privacy_consent':True,'last_donation':''}
        payload.update(extra)
        response=self.post(client or self.donor,'donor',payload)
        self.assertEqual(response.status_code,200,response.json)

    def request(self,**extra):
        payload={'blood_group':'O+','units':2,'hospital':'Test Hospital','city':'Bengaluru','lat':12.9716,'lon':77.5946}
        payload.update(extra)
        return self.post(self.recipient,'requests',payload)

    def inbox(self):
        return self.donor.get('/api/dashboard').json['inbox']

    def acceptance(self,**extra):
        payload={'action':'accept','never_donated':True,'well_today':True,'clinical_consent':True}
        payload.update(extra)
        return payload

    def test_end_to_end_accept_and_owner_visibility(self):
        self.profile()
        response=self.request()
        self.assertEqual(response.status_code,201)
        self.assertEqual(response.json['matched'],1)
        inbox=self.inbox()
        self.assertEqual(inbox[0]['whatsapp_status'],'dry-run')
        result=self.post(self.donor,f'matches/{inbox[0]["id"]}/respond',self.acceptance())
        self.assertEqual(result.status_code,200,result.json)
        dashboard=self.recipient.get('/api/dashboard').json
        self.assertEqual(dashboard['requests'][0]['matches'][0]['status'],'accepted')
        self.assertIn('volunteer accepted',dashboard['notifications'][0]['message'])
        self.assertNotIn('phone',str(dashboard))
        self.assertNotIn('lat',dashboard['requests'][0])
        self.assertEqual(self.other.get('/api/dashboard').json['requests'],[])

    def test_recent_donation_blocks_acceptance(self):
        self.profile(); self.request(); mid=self.inbox()[0]['id']
        result=self.post(self.donor,f'matches/{mid}/respond',self.acceptance(never_donated=False,last_donation=(date.today()-timedelta(days=89)).isoformat()))
        self.assertEqual(result.status_code,400)
        self.assertEqual(self.inbox()[0]['status'],'pending')
        result=self.post(self.donor,f'matches/{mid}/respond',self.acceptance(never_donated=False,last_donation=(date.today()-timedelta(days=120)).isoformat()))
        self.assertEqual(result.status_code,200)

    def test_requires_complete_screening(self):
        self.profile();self.request();mid=self.inbox()[0]['id']
        for payload in [self.acceptance(well_today=False),self.acceptance(never_donated=False),self.acceptance(clinical_consent=False),self.acceptance(last_donation='2000-01-01')]:
            self.assertEqual(self.post(self.donor,f'matches/{mid}/respond',payload).status_code,400)

    def test_decline_is_final(self):
        self.profile();self.request();mid=self.inbox()[0]['id']
        self.assertEqual(self.post(self.donor,f'matches/{mid}/respond',{'action':'decline'}).status_code,200)
        self.assertEqual(self.post(self.donor,f'matches/{mid}/respond',self.acceptance()).status_code,409)

    def test_other_account_cannot_respond_or_close(self):
        self.profile();rid=self.request().json['id'];mid=self.inbox()[0]['id']
        self.assertEqual(self.post(self.other,f'matches/{mid}/respond',self.acceptance()).status_code,404)
        self.assertEqual(self.post(self.other,f'requests/{rid}/close',{}).status_code,404)
        self.assertEqual(self.post(self.recipient,f'requests/{rid}/close',{}).status_code,200)
        self.assertEqual(self.post(self.donor,f'matches/{mid}/respond',self.acceptance()).status_code,409)

    def test_matching_filters(self):
        for extra in [{'blood_group':'B+'},{'available':False},{'last_donation':date.today().isoformat()},{'lat':28.6,'lon':77.2}]:
            self.profile(**extra)
            self.assertEqual(self.request().json['matched'],0,extra)

    def test_nearest_five_only_and_self_excluded(self):
        self.profile(client=self.recipient)
        for i in range(7):
            c=self.account(f'Donor {i}',f'near{i}@example.test')
            self.profile(client=c,lat=12.97+i*.01)
        self.assertEqual(self.request().json['matched'],5)
        matches=self.recipient.get('/api/dashboard').json['requests'][0]['matches']
        self.assertEqual([m['distance'] for m in matches],sorted(m['distance'] for m in matches))
        self.assertNotIn('Recipient',[m['name'] for m in matches])

    def test_csrf_and_auth(self):
        self.assertEqual(self.recipient.post('/api/requests',json={}).status_code,403)
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.get('/api/dashboard').status_code,401)
        self.assertEqual(self.post(anonymous,'requests',{}).status_code,401)

    def test_validation_and_samples(self):
        for extra in [{'units':0},{'blood_group':'Z+'},{'lat':0},{'lat':'NaN'},{'hospital':''}]:
            self.assertEqual(self.request(**extra).status_code,400)
        result=self.recipient.get('/api/centres?lat=12.9716&lon=77.5946')
        self.assertEqual(result.status_code,200)
        self.assertTrue(all(c['sample'] for c in result.json['centres']))
        self.assertEqual(result.json['centres'][0]['distance_km'],0)
        self.assertEqual(self.recipient.get('/api/centres?lat=91&lon=77').status_code,400)

    def test_live_whatsapp_requires_verified_phone(self):
        self.profile()
        with patch.dict(os.environ,{'WHATSAPP_MODE':'live'}):
            self.request()
        self.assertEqual(self.inbox()[0]['whatsapp_status'],'skipped')
        with patch('urllib.request.urlopen') as network:
            result=self.app.test_cli_runner().invoke(args=['send-whatsapp'])
            self.assertEqual(result.exit_code,0)
            network.assert_not_called()

    def test_consent_and_notifications(self):
        self.profile(whatsapp_consent=False);self.request()
        self.assertEqual(self.inbox()[0]['whatsapp_status'],'skipped')
        self.assertEqual(len(self.donor.get('/api/dashboard').json['notifications']),1)
        self.post(self.donor,'notifications/read',{})
        self.assertEqual(self.donor.get('/api/dashboard').json['notifications'][0]['read'],1)

    def test_provider_payload_and_uncertain_delivery_are_not_retried(self):
        self.profile()
        connection=sqlite3.connect(self.app.config['DATABASE'])
        connection.execute('UPDATE donors SET phone_verified=1')
        connection.commit()
        settings={'WHATSAPP_MODE':'live','WHATSAPP_TOKEN':'test-only-token',
                  'WHATSAPP_PHONE_NUMBER_ID':'12345','WHATSAPP_TEMPLATE':'blood_donor_request',
                  'WHATSAPP_API_VERSION':'v23.0'}
        with patch.dict(os.environ,settings):
            self.request()
            self.assertEqual(self.inbox()[0]['whatsapp_status'],'queued')
            with patch('urllib.request.urlopen') as network:
                network.return_value.__enter__.return_value.read.return_value=b'{"messages":[{"id":"test-id"}]}'
                result=self.app.test_cli_runner().invoke(args=['send-whatsapp'])
                self.assertEqual(result.exit_code,0,result.output)
                payload=json.loads(network.call_args.args[0].data)
                self.assertEqual(payload['template']['components'][0]['parameters'][0]['text'],'1')
                self.assertNotIn('hospital',str(payload))
                self.assertEqual(self.inbox()[0]['whatsapp_status'],'submitted')
                self.app.test_cli_runner().invoke(args=['send-whatsapp'])
                self.assertEqual(network.call_count,1)
            self.request()
            with patch('urllib.request.urlopen',side_effect=TimeoutError) as network:
                result=self.app.test_cli_runner().invoke(args=['send-whatsapp'])
                self.assertEqual(result.exit_code,0)
                self.assertEqual(self.inbox()[0]['whatsapp_status'],'unknown')
                self.app.test_cli_runner().invoke(args=['send-whatsapp'])
                self.assertEqual(network.call_count,1)
        connection.close()

    def test_login_logout_and_duplicates(self):
        self.post(self.donor,'logout',{})
        self.assertIsNone(self.donor.get('/api/session').json['user'])
        self.assertEqual(self.post(self.donor,'login',{'email':'donor@example.test','password':'bad-password-123'}).status_code,401)
        self.assertEqual(self.post(self.donor,'login',{'email':'donor@example.test','password':'test-password-123'}).status_code,200)
        self.assertEqual(self.post(self.other,'register',{'email':'donor@example.test','name':'Duplicate','password':'test-password-123'}).status_code,409)


if __name__=='__main__':
    unittest.main()
