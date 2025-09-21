import os, base64, mimetypes, json, re
from typing import List, Dict, Any, Tuple
from collections import Counter, defaultdict
from openai import OpenAI
from PIL import Image
from pillow_heif import register_heif_opener

from dotenv import load_dotenv
import os


load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
organization = os.getenv("OPENAI_ORGANIZATION")

client = OpenAI( api_key = api_key, organization = organization )

# =============== 설정 ===============
# CONTENT_IMAGES: List[str] = ["img4.HEIC"]  # 1~N장 아무거나
# CONTENT_IMAGES: List[str] = ["img5.JPG", "img6.jpg"]  # 1~N장 아무거나
# CONTENT_IMAGES: List[str] = ["img7.HEIC", "img8.jpg"]  # 1~N장 아무거나
# CONTENT_IMAGES: List[str] = ["img1.JPG", "img2.JPG", "img3.JPG"]  # 1~N장 아무거나

CONTENT_IMAGES: List[str] = ["img007.jpeg", "img008.jpeg"]  # 1~N장 아무거나



OUTPUT_IMAGE   = "final_hybrid_required.png"

# 세로: "1024x1536" / 가로: "1536x1024" / 정사각: "1024x1024" / "auto"
SIZE           = "1024x1536"

VISION_MODEL   = "gpt-4o-mini"  # 비전 요약용
IMAGE_MODEL    = "gpt-image-1"  # 이미지 생성(조직 인증/결제 필요)

# 스타일(고정 템플릿)
FIXED_STYLE = (
    "Childlike crayon/colored-pencil illustration on paper. "
    "Visible paper texture, uneven strokes, thick outlines. "
    "Warm, cozy lighting with soft shadows. "
    "Simplified but recognizable shapes. "
    "Limited warm palette (browns/oranges) with soft greens as accents. "
    "No photorealism, no extra text, no watermarks or logos."
)

# 1) 풍부 캡션(자연어) 프롬프트
CAPTION_PROMPT = (
    "Describe WHAT is in this image (not art style). Be exhaustive and concrete: "
    "list notable objects, colors, textures, relative sizes, spatial relations, "
    "and any readable text EXACTLY as seen."
)

# 2) MUST-INCLUDE(JSON) 프롬프트: 대표 1개 + MUST 6개
MUST_JSON_PROMPT = (
    "From the caption below, output VALID JSON with this schema:\n"
    "{\n"
    '  "representative": "<one short noun phrase capturing the most distinctive element of THIS image>",\n'
    '  "must": ["<exactly 6 short noun phrases>"]\n'
    "}\n"
    "Rules: 'must' must contain EXACTLY 6 unique items. "
    "'representative' must be one of 'must'. Keep concise; no prose. Output JSON ONLY."
)

# 여러 MUST 리스트 병합 가이드(백업용 텍스트 병합에 사용 가능)
MERGE_HINT = (
    "Prefer items that appear across multiple images, but ensure diversity."
)

# ===========================
# 초기화/유틸
# ===========================
register_heif_opener()  # HEIC 지원

def require_file(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"파일 없음: {path}")

def ensure_supported_format(image_path: str) -> str:
    """
    HEIC/손상/비표준 등도 JPEG로 안전 변환.
    """
    supported_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    base, ext = os.path.splitext(image_path)
    ext_lower = ext.lower()

    try:
        with Image.open(image_path) as im:
            im.verify()  # 간단 검증
        ok = True
    except Exception:
        ok = False

    if ext_lower in supported_exts and ok:
        return image_path

    new_path = base + ".jpeg"
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        im.save(new_path, "JPEG")
    return new_path

def to_data_uri(image_path: str) -> str:
    safe = ensure_supported_format(image_path)
    mime, _ = mimetypes.guess_type(safe.lower())
    if mime is None:
        mime = "image/jpeg"
    with open(safe, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# ===========================
# 비전 호출 (요약 단계)
# ===========================
def chat_vision_image_caption(client: OpenAI, image_path: str) -> str:
    """이미지 1장 → 풍부한 캡션(자연어)"""
    data_uri = to_data_uri(image_path)
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.1,  # 일관성↑
        messages=[{
            "role": "user",
            "content": [
                {"type":"text","text": CAPTION_PROMPT},
                {"type":"image_url","image_url":{"url": data_uri}},
            ],
        }],
    )
    return resp.choices[0].message.content.strip()

def chat_must_json_from_caption(client: OpenAI, caption: str) -> Dict[str, Any]:
    """캡션 → JSON: representative 1개 + must 6개"""
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.0,  # 결정적
        messages=[{
            "role":"user",
            "content":[{"type":"text","text": MUST_JSON_PROMPT + "\n\nCaption:\n" + caption}]
        }],
    )
    txt = resp.choices[0].message.content.strip()
    # JSON 파싱 보정
    try:
        data = json.loads(txt)
    except json.JSONDecodeError:
        txt = txt[txt.find("{"): txt.rfind("}")+1]
        data = json.loads(txt)
    # 방어코드
    rep = (data.get("representative") or "").strip()
    must = [m.strip() for m in (data.get("must") or []) if m.strip()]
    # 6개 보장 실패 시, 캡션 재요약으로 보충하지 않고 그대로 사용(생성 프롬프트에서 강하게 요구)
    return {"representative": rep, "must": must[:6]}

# ===========================
# MUST 병합 로직 (이미지별 1개 필수 보장)
# ===========================
def _norm(s: str) -> str:
    # 간단 정규화: 소문자/공백/기호 정리
    s = s.lower().strip()
    s = re.sub(r"[\s]+", " ", s)
    s = re.sub(r"[^\w\s\-+/&]", "", s)
    return s

def select_required_and_global(must_jsons: List[Dict[str, Any]], target_total: int = 6) -> Tuple[List[str], List[str]]:
    """
    - 각 이미지의 representative를 우선으로 '필수(required_per_image)'에 1개씩 담는다.
    - 대표가 중복되면, 해당 이미지의 'must' 목록에서 대체 항목을 선택(중복 회피).
    - 나머지 자리는 전체 must 합집합에서 '자주 등장한 항목' 순으로 채워 6개 맞춤.
    반환: (required_per_image, global_must)
    """
    required_per_image: List[str] = []
    used_norm = set()

    # 1) 이미지별 대표 우선 선택
    for j in must_jsons:
        chosen = None
        cand = [j.get("representative","")] + j.get("must", [])
        for c in cand:
            n = _norm(c)
            if c and n not in used_norm:
                chosen = c
                used_norm.add(n)
                break
        if chosen:
            required_per_image.append(chosen)

    # 2) 글로벌 후보 풀
    pool = []
    for j in must_jsons:
        pool.extend([m for m in j.get("must", []) if m])

    # 3) 빈도 기반으로 나머지 채우기
    freq = Counter([_norm(x) for x in pool])
    norm2orig = {}
    # 첫 등장 원문 보존
    for x in pool:
        n = _norm(x)
        norm2orig.setdefault(n, x)

    global_must = list(required_per_image)  # 시작점: 필수 항목 포함
    for n, _count in freq.most_common():
        if n not in used_norm:
            global_must.append(norm2orig[n])
            used_norm.add(n)
        if len(global_must) >= target_total:
            break

    # 혹시 target_total보다 아직 적으면(입력이 너무 빈약하면) 그냥 필수만 사용
    global_must = global_must[:target_total]
    return required_per_image, global_must

# ===========================
# 최종 프롬프트 생성
# ===========================
def build_final_prompt_hybrid_required(captions: List[str],
                                       required_per_image: List[str],
                                       global_must: List[str],
                                       size: str) -> str:
    aspect = {
        "1024x1536":"portrait 2:3 (1024x1536)",
        "1536x1024":"landscape 3:2 (1536x1024)",
        "1024x1024":"square 1:1 (1024x1024)",
        "auto":"auto"
    }.get(size, size)

    captions_block = "\n".join(f"- {c}" for c in captions)
    required_block = "\n".join(f"- {x}" for x in required_per_image)
    global_block   = "\n".join(f"- {x}" for x in global_must)

    return f"""
Create one cohesive scene in the following FIXED STYLE.

FIXED STYLE:
{FIXED_STYLE}

Use these rich CAPTIONS as nuanced guidance (do not ignore small accessories/textures):
{captions_block}

REQUIRED (at least one from EACH input image; DO NOT OMIT any of these):
{required_block}

GLOBAL MUST (complete to 6; keep clearly visible):
{global_block}

Output:
- Respect relative sizes/relations implied by the captions.
- Keep 3–5 primary objects; minimal clutter; natural depth/perspective.
- Aspect: {aspect}
- No photorealism, no extra text/logos/watermarks.
""".strip()

# ===========================
# 메인 파이프라인
# ===========================
def run_images(images):
    if not CONTENT_IMAGES:
        raise ValueError("CONTENT_IMAGES에 최소 1개 이상의 이미지 경로를 넣어주세요.")
    for p in CONTENT_IMAGES:
        require_file(p)

    # 1) 이미지마다 풍부한 캡션
    print("[1/5] Generating rich captions…")
    captions = [chat_vision_image_caption(client, p) for p in CONTENT_IMAGES]

    # 2) 각 캡션에서 MUST JSON(대표1 + MUST6) 추출
    print("[2/5] Extracting per-image MUST JSON…")
    must_jsons = [chat_must_json_from_caption(client, c) for c in captions]

    # 3) '이미지별 최소 1개' 필수 보장 + 6개 리스트 완성
    print("[3/5] Selecting REQUIRED per image and GLOBAL MUST(=6)…")
    required_per_image, global_must = select_required_and_global(must_jsons, target_total=6)

    # 4) 최종 프롬프트 생성
    print("[4/5] Building final prompt…")
    final_prompt = build_final_prompt_hybrid_required(captions, required_per_image, global_must, SIZE)
    # 디버깅 원하면 주석 해제
    # print("\n==== FINAL PROMPT ====\n", final_prompt, "\n======================\n")

    # 5) 이미지 생성
    print("[5/5] Generating image…")
    gen = client.images.generate(
        model=IMAGE_MODEL,
        prompt=final_prompt,
        size=SIZE,  # 지원: 1024x1024 / 1024x1536 / 1536x1024 / auto
    )
    b64 = gen.data[0].b64_json
    with open(OUTPUT_IMAGE, "wb") as f:
        f.write(base64.b64decode(b64))

    print(f"\n✅ Done! Saved -> {OUTPUT_IMAGE}")

    return OUTPUT_IMAGE
