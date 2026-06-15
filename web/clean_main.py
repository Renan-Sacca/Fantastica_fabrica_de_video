import re

with open('app/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from app.video_types import all_video_types, get_video_type", "from app.video_types import all_video_types, get_video_type\nfrom app.routers import whatsapp")

content = content.replace("templates = Jinja2Templates(directory=str(TEMPLATES_DIR))", "templates = Jinja2Templates(directory=str(TEMPLATES_DIR))\n\napp.include_router(whatsapp.router)")

# Remove old UI routes
content = re.sub(r"@app\.get\(\"/jobs\", response_class=HTMLResponse\).*?@app\.get\(\"/api/jobs\"\)", '@app.get("/api/jobs")', content, flags=re.DOTALL)

# Remove edit route
content = re.sub(r"@app\.post\(\"/video/\{job_id\}/edit\"\).*?@app\.get\(\"/api/drive/media/\{file_id\}\"\)", '@app.get("/api/drive/media/{file_id}")', content, flags=re.DOTALL)

# Remove duplicate route
content = re.sub(r"@app\.post\(\"/video/\{job_id\}/duplicate\"\).*?@app\.post\(\"/api/sync\"\)", '@app.post("/api/sync")', content, flags=re.DOTALL)

with open('app/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("main.py cleaned successfully!")
