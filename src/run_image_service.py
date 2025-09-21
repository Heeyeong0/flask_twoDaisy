
def extract_image_filenames(req, max_count=3):
    """
    요청 JSON에서 이미지 파일명 목록 추출
    예: {"files": ["a.jpg", "b.png"]}
    """
    data = req.get_json(silent=True) or {}
    files = data.get("files", [])
    if not isinstance(files, list):
        raise ValueError("files 필드는 리스트여야 합니다.")
    return files[:max_count]