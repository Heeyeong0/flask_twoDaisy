from openai import OpenAI
from dotenv import load_dotenv
import os
from flask import Flask, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/')
def hello():
    return "Hello, Flask!"


@app.route('/analyze-images', methods=['POST'])
def analyze_images_route():
    files = get_uploaded_images(request)
    return ""
    
   
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



@app.route('/openai')  
def openai():

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")  # 환경 변수에서 키 읽기
    client = OpenAI(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "이 그림에 대해서 설명해줘"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://images.unsplash.com/photo-1736264335247-8ec5664c8328?q=80&w=1887&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
                    }
                }
            ]
        }
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 응답 생성에 사용할 모델 지정
        messages=messages # 대화 기록을 입력으로 전달
    )

    pro_res = response.choices[0].message.content

    print(pro_res)

    system_prompt = f'''
        Soft pastel-crayon illustration of { pro_res }, 
        warm sun-drenched palette, gentle children’s-storybook style, 
        visible grainy texture, simple rounded shapes, 
        flat overhead lighting, cozy and cheerful mood, 
        reminiscent of hand-drawn crayon artwork
        '''

    image_response = client.images.generate(
        model="dall-e-3",
        prompt=system_prompt,
        n=1,
        size="1024x1024"
    )

    image_response.data[0].url


    return "This is the about page."

if __name__ == '__main__':
    app.run(debug=True, port=8000)
