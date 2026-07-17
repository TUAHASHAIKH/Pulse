import httpx
import asyncio
import json

async def test_review_api():
    diff = """
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@
 def login(user_email, password):
-    query = "SELECT * FROM users WHERE email = %s"
-    cursor.execute(query, (user_email,))
+    query = f"SELECT * FROM users WHERE email = '{user_email}' AND password = '{password}'"
+    cursor.execute(query)
+    API_KEY = "sk-live-1234567890"
"""

    payload = {
        "diff": diff
    }

    print("Sending POST /api/review request with raw diff...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post("http://127.0.0.1:8000/api/review", json=payload, timeout=10)
            print(f"Status: {response.status_code}")
            print(json.dumps(response.json(), indent=2))
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_review_api())
