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

