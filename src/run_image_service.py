from image_utils import UPLOAD_DIR

# ---- 단순 URL 추출 ----
def extract_image_urls(req, max_count=3):
    data = req.get_json(silent=True) or {}
    urls = []

    if isinstance(data.get("urls"), list):
        urls = data["urls"]
    elif data.get("url"):
        urls = [data["url"]]

    return urls[:max_count]


# ---- URL → 파일 객체 ----
def load_local_files(urls):
    files = []
    for u in urls:
        if u.startswith("/static/uploads/"):
            path = UPLOAD_DIR / u.replace("/static/uploads/", "")
            if path.exists():
                files.append(open(path, "rb"))  # run_images는 file-like object만 있으면 됨
    return files
