from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello, Flask!"

@app.route('/about')  # ✅ 이 부분이 꼭 있어야 해요!
def about():
    return "This is the about page."

if __name__ == '__main__':
    app.run(debug=True)
