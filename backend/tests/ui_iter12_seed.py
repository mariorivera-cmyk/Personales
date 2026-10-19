# Seed a TEST_ company for UI testing of skip-guide flow (prints credentials)
import os, time, requests, sys
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
st = str(int(time.time()))
email = f"test_ui12_{st}@example.com"
r = requests.post(f"{API}/signup", json={"company_name": f"TEST_UI12 {st}", "email": email, "password": "Test12345!",
                                         "whatsapp_number": f"+5026{st[-7:]}", "slug": f"test-ui12-{st}"})
print(r.status_code, email, f"test-ui12-{st}")
