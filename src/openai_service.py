import os, json, base64, asyncio, aiofiles, time, io, re, uuid
from typing import List, Dict, Any, Tuple
from collections import Counter
from PIL import Image
from pillow_heif import register_heif_opener
from openai import AsyncOpenAI
from dotenv import load_dotenv
from pathlib import Path

from src.image_utils import UPLOAD_DIR

# ===========================
# 설정
# ===========================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
organization = os.getenv("OPENAI_ORGANIZATION")

async_client = AsyncOpenAI(api_key=api_key)

VISION_MODEL = "gpt-4o"
IMAGE_MODEL = "gpt-image-1"
SIZE = "1024x1024"

BASE_DIR = Path(__file__).resolve().parent.parent  # src 상위 = 프로젝트 루트
OUTPUT_DIR = BASE_DIR / "static" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

output_filename = f"{uuid.uuid4().hex}.png"
OUTPUT_IMAGE = OUTPUT_DIR / output_filename

CAPTION_PROMPT = (
    "Describe the image as follows: count and describe every person present (state if only one person, what they are doing, wearing, any emotion visible), list main food or objects present, colors, text, positions. Be concise and accurate."
)
MUST_JSON_PROMPT = (
    "From the caption below, output VALID JSON with this schema:\n"
    "{\n"
    '  "representative": "<one short noun phrase capturing the most distinctive element of THIS image>",\n'
    '  "must": ["<exactly 6 short noun phrases>"]\n'
    "}\n"
    "Rules: 'must' must contain EXACTLY 6 unique items. "
    "'representative' must be one of 'must'. The list should include any detected people and specific foods or objects. Keep concise; no prose. Output JSON ONLY."
)
FIXED_STYLE = (
    "Childlike crayon illustration. Paper texture, thick outlines. "
    "Keep the original photo's colors faithfully, do not shift overall color scheme. "
    "No text/logos."
)

# ===========================
# 안전 필터링
# ===========================
def sanitize_for_safety(text: str) -> str:
    ban_words = ['naked', 'nudity', 'explicit', 'sexual']
    safe_text = text
    for ban in ban_words:
        safe_text = re.sub(rf"\\b{ban}\\b", "", safe_text, flags=re.IGNORECASE)
    return safe_text.strip(",. ")

def build_safe_prompt(required: List[str], global_must: List[str], captions: List[str]) -> str:
    merged = ', '.join(required + global_must)
    merged = sanitize_for_safety(merged)
    captions_text = ' '.join([sanitize_for_safety(c) for c in captions])
    return f"""
{FIXED_STYLE}
Include these elements: {merged}
Scene details: {captions_text}
Do not invent faces or people not present in the scene. Show only detected people as cartoon shapes if any.
No explicit body detail, no text, no watermarks.
Aspect ratio: {SIZE.replace('x', ' x ')}
""".strip()

# ===========================
# 유틸리티 함수
# ===========================
register_heif_opener()

def require_file(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"파일 없음: {path}")

def ensure_supported_format(image_path: str) -> str:
    supported_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    base, ext = os.path.splitext(image_path)
    if ext.lower() in supported_exts:
        try:
            with Image.open(image_path) as im:
                im.verify()
            return image_path
        except:
            pass
    new_path = base + ".jpeg"
    with Image.open(image_path) as im:
        im = im.convert("RGB")
        im.save(new_path, "JPEG", quality=85)
    return new_path

async def optimized_to_data_uri(image_path: str) -> str:
    safe_path = ensure_supported_format(str(image_path))
    async with aiofiles.open(safe_path, 'rb') as f:
        content = await f.read()
    with Image.open(io.BytesIO(content)) as img:
        if max(img.size) > 1024:
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=80, optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"

def _norm(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\s]+", " ", s)
    s = re.sub(r"[^\w\s\-+/&]", "", s)
    return s

def select_required_and_global(must_jsons: List[Dict[str, Any]], target_total: int = 6) -> Tuple[List[str], List[str]]:
    required_per_image: List[str] = []
    used_norm = set()
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
    pool = []
    for j in must_jsons:
        pool.extend([m for m in j.get("must", []) if m])
    freq = Counter([_norm(x) for x in pool])
    norm2orig = {}
    for x in pool:
        n = _norm(x)
        norm2orig.setdefault(n, x)
    global_must = list(required_per_image)
    for n, _ in freq.most_common():
        if n not in used_norm:
            global_must.append(norm2orig[n])
            used_norm.add(n)
        if len(global_must) >= target_total:
            break
    return required_per_image, global_must[:target_total]

# ===========================
# 비동기 API 호출 함수들
# ===========================
async def async_vision_caption(image_path: str) -> str:
    data_uri = await optimized_to_data_uri(image_path)
    prompt = CAPTION_PROMPT
    resp = await async_client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.2,
        max_tokens=180,
        messages=[{
            "role": "user",
            "content": [
                {"type":"text","text": prompt},
                {"type":"image_url","image_url":{"url": data_uri, "detail": "low"}}
            ],
        }],
    )
    return resp.choices[0].message.content.strip()

async def async_must_json(caption: str) -> Dict[str, Any]:
    resp = await async_client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0.0,
        max_tokens=90,
        messages=[{
            "role":"user",
            "content": MUST_JSON_PROMPT + "\n\nCaption:\n" + caption[:250]
        }],
    )
    txt = resp.choices[0].message.content.strip()
    try:
        start = txt.find("{")
        end = txt.rfind("}") + 1
        if start >= 0 and end > start:
            txt = txt[start:end]
        data = json.loads(txt)
    except:
        data = {"representative": "object", "must": ["item1","item2","item3","item4","item5","item6"]}
    rep = (data.get("representative") or "").strip()
    must = [m.strip() for m in (data.get("must") or []) if m.strip()]
    return {"representative": rep, "must": must[:6]}

# ===========================
# 실행 함수와 이미지 경로 처리
# ===========================
def run_images(urls):
    local_paths = []

    if not urls:
        raise ValueError("최소 1개 이상의 이미지 경로를 넣어주세요.")
    for p in urls:
        print(p)
        path = UPLOAD_DIR / p
        local_paths.append(path)
    return asyncio.run(ultra_optimized_main(local_paths))

# ===========================
# 메인 비동기 처리 함수
# ===========================
async def ultra_optimized_main(local_paths):
    for p in local_paths:
        require_file(str(p))

    print("🚀 초고속 저비용 처리 시작...")
    start_time = time.time()

    # 1) 이미지 병렬 분석
    print("[1/3] 이미지 병렬 분석 중...")
    caption_tasks = [async_vision_caption(str(img_path)) for img_path in local_paths]
    captions = await asyncio.gather(*caption_tasks)

    # 2) 특징 병렬 추출
    print("[2/3] 특징 병렬 추출 중...")
    json_tasks = [async_must_json(c) for c in captions]
    must_jsons = await asyncio.gather(*json_tasks)

    # 3) 요소 선택 및 이미지 생성
    print("[3/3] 핵심 요소 선택 및 그림 생성 중...")
    required_per_image, global_must = select_required_and_global(must_jsons, target_total=6)
    final_prompt = build_safe_prompt(required_per_image, global_must, captions)
    image_task = async_client.images.generate(model=IMAGE_MODEL, prompt=final_prompt, size=SIZE, quality="medium")
    gen_result = await image_task

    # 결과 저장
    b64 = gen_result.data[0].b64_json
    with open(OUTPUT_IMAGE, "wb") as f:
        f.write(base64.b64decode(b64))
    elapsed = time.time() - start_time
    print(f"\n✅ 완료! 총 소요시간: {elapsed:.1f}초")
    print(f"📸 생성된 이미지: {OUTPUT_IMAGE}")

    filename = os.path.basename(OUTPUT_IMAGE)
    print(filename)

    return filename