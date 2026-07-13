# Auth Testing Playbook (Emergent Google Auth)

## Step 1: Create Test User & Session in MongoDB

```bash
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.user.' + Date.now() + '@example.com',
  name: 'Test User',
  picture: 'https://via.placeholder.com/150',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Test Backend
```bash
curl -X GET "$REACT_APP_BACKEND_URL/api/auth/me" -H "Authorization: Bearer $TOKEN"
```

## Step 3: Browser via Playwright cookies
```python
await context.add_cookies([{
  "name": "session_token",
  "value": TOKEN,
  "domain": "cashflow-hub-444.preview.emergentagent.com",
  "path": "/",
  "httpOnly": True, "secure": True, "sameSite": "None"
}])
```
