from openai import OpenAI

from flask import Flask, request
from flask_cors import CORS
from openai_test import run_images

from image_utils import *

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello():
    return "Hello, Flask!"


@app.route('/analyze-images', methods=['POST'])
def analyze_images_route():
    files = get_uploaded_images(request)
    return ""


# ------- 이미지 업로드 -------

@app.route("/upload-image", methods=["POST"])
def upload_image():
    """
    단일 이미지 업로드
    - form-data: { image: <파일> }
    응답: {"url": "..."}
    """
    file = request.files.get("image")
    if not file or file.filename == "":
        return jsonify({"error": "image 필드로 파일을 전송하세요."}), 400

    try:
        url = save_file_and_get_url(file)  # 앞서 만든 공통 유틸 사용
        return jsonify({"url": url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def get_uploaded_images(req, max_count=3):
    file_keys = req.files.keys()
    print("📂 업로드된 파일 키 목록:", list(file_keys))

    files = []
    for i in range(1, max_count + 1):
        file = req.files.get(f'image{i}')
        if file:
            print(f"✅ image{i} 업로드됨 - filename: {file.filename}, content_type: {file.content_type}")
            files.append(file)
        else:
            print(f" image{i} 없음")
    return files



if __name__ == '__main__':
    app.run(debug=True, port=8000)
