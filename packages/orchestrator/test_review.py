import requests

payload = {
    "source": "cli",
    "diff": "diff --git a/app.js b/app.js\nnew file mode 100644\nindex 0000000..8b13789\n--- /dev/null\n+++ b/app.js\n@@ -0,0 +1,5 @@\n+const query = \"SELECT * FROM users WHERE id = \" + req.params.id;\n+for(let i=0; i<1000000; i++) { doSomething(); }",
    "changed_files": ["app.js"]
}

resp = requests.post("http://localhost:8000/api/review", json=payload)
print(resp.status_code)
print(resp.json())
