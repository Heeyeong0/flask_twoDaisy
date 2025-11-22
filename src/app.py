import os
import calendar

from flask import request, jsonify, send_from_directory, abort
from werkzeug.exceptions import HTTPException

from sqlalchemy import func, and_

from src.db.session import SessionLocal, Base, engine
from src.models.image_record import ImageRecord
from src.openai_service import OUTPUT_DIR, run_images

from image_utils import *
from run_image_service import *



app = Flask(__name__)
CORS(app)

Base.metadata.create_all(engine)

# Base.metadata.create_all(engine)

@app.route('/')
def hello():

    return "Hello, Flask!"


@app.route("/images/daily-latest", methods=["GET"])
def get_daily_latest():
    """
    예)
      - /images/daily-latest?year=2025&month=2
          -> [ { "day": 1, "image_name": "" }, ... ]  // 월 전체
      - /images/daily-latest?year=2025&month=2&day=3
          -> { "day": 3, "image_name": "xxx.png" }    // 해당 일만
    """
    # year, month 파싱
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        return jsonify({"error": "year, month를 정수로 전달하세요."}), 400

    # day(옵션) 파싱
    day_param = request.args.get("day")
    try:
        day = int(day_param) if day_param is not None else None
    except ValueError:
        return jsonify({"error": "day는 정수여야 합니다."}), 400

    db = SessionLocal()

    # 공통: 날짜 라벨
    day_label = func.strftime('%Y-%m-%d', ImageRecord.created_at)

    # ─────────────────────────────────────────────
    # A) day가 주어진 경우: 해당 '하루'만 최신 이미지 1개 반환
    # ─────────────────────────────────────────────
    if day is not None:
        # 유효 일수 체크
        last_day = calendar.monthrange(year, month)[1]
        if not (1 <= day <= last_day):
            return jsonify({"error": f"day는 1~{last_day} 범위여야 합니다."}), 400

        target_key = f"{year:04d}-{month:02d}-{day:02d}"

        row = (
            db.query(ImageRecord.image_name)
              .filter(day_label == target_key)
              .order_by(ImageRecord.created_at.desc())
              .first()
        )

        return jsonify({
            "day": day,
            "image_name": row[0] if row else ""
        })

    # ─────────────────────────────────────────────
    # B) day가 없는 경우: 월 전체(1~말일) 리스트 반환
    # ─────────────────────────────────────────────
    days_in_month = calendar.monthrange(year, month)[1]

    # 날짜별 최신 created_at 서브쿼리
    subq = (
        db.query(
            day_label.label('day'),
            func.max(ImageRecord.created_at).label('max_ts')
        )
        .filter(func.strftime('%Y', ImageRecord.created_at) == f"{year:04d}")
        .filter(func.strftime('%m', ImageRecord.created_at) == f"{month:02d}")
        .group_by(day_label)
        .subquery()
    )

    rows = (
        db.query(
            day_label.label('day'),
            ImageRecord.image_name
        )
        .join(subq,
              and_(day_label == subq.c.day,
                   ImageRecord.created_at == subq.c.max_ts))
        .all()
    )

    latest_by_day = {d: name for d, name in rows}

    result = []
    for d in range(1, days_in_month + 1):
        date_key = f"{year:04d}-{month:02d}-{d:02d}"
        result.append({
            "day": d,
            "image_name": latest_by_day.get(date_key, "")
        })

    return jsonify(result)



@app.route("/delete-image", methods=["DELETE"])
def delete_image_by_name():
    """
    DELETE /delete-image?name=xxx.png

    → { "deleted": "xxx.png" }
    or
    → { "deleted": "" }   (없음)
    """

    image_name = request.args.get("name")

    if not image_name:
        return jsonify({"error": "name 쿼리 파라미터가 필요합니다."}), 400

    db = SessionLocal()

    # 동일 파일명 여러 건이면 created_at 최신 1건 삭제
    record = (
        db.query(ImageRecord)
          .filter(ImageRecord.image_name == image_name)
          .order_by(ImageRecord.created_at.desc())
          .first()
    )

    if not record:
        return jsonify({"deleted": ""})

    # 파일 삭제
    file_path = os.path.join(OUTPUT_DIR, record.image_name)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            pass

    # DB 삭제
    db.delete(record)
    db.commit()

    return jsonify({"deleted": image_name})


@app.route('/analyze-images', methods=['POST'])
def analyze_images_route():
    """
    JSON:
    - {"url": "/static/uploads/a.png"}
    - {"urls": ["/static/uploads/a.png", "/static/uploads/b.jpg"]}
    """
    urls = extract_image_filenames(request)
    if not urls:
        raise ValueError("이미지 URL이 필요합니다. (url 또는 urls)")

    result = run_images(urls)

    image_name = result

    # 2) DB 저장
    db = SessionLocal()
    record = ImageRecord(image_name=image_name)
    print("image_name" , image_name)
    db.add(record)
    db.commit()
    db.refresh(record)

    return jsonify({
        "result_image_name": result  # 키를 붙여 JSON으로

    })


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
        file_name = save_file_and_get_name(file)  # 앞서 만든 공통 유틸 사용
        return jsonify({"name": file_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 400



@app.route("/get-image/<filename>", methods=["GET"])
def get_image(filename):
    """
    저장된 이미지 1장을 반환
    URL: /get-image/<파일명>
    예: /get-image/abc123.png
    """
    try:
        return send_from_directory(
            OUTPUT_DIR,       # static/uploads 경로 (Path → str 변환 필요할 수 있음)
            filename,
            as_attachment=False  # True면 다운로드, False면 브라우저에서 직접 보여줌
        )
    except FileNotFoundError:
        abort(404, description=f"이미지 없음: {filename}")



@app.errorhandler(Exception)
def handle_exception(e):
    # HTTPException (Flask/werkzeug 기본 예외: 404, 400 등)
    if isinstance(e, HTTPException):
        return jsonify({"error": e.description}), e.code

    # 나머지 일반 Exception → 500
    return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)
