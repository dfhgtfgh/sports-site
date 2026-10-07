from flask import Flask, jsonify, render_template, request
from parser import fetch_news, fetch_matches, fetch_article

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/matches")
def api_matches():
    category = request.args.get("category", "all")
    matches = fetch_matches()
    if category and category != "all":
        matches = [m for m in matches if m.get("sport") == category]
    return jsonify(matches)


@app.route("/api/news")
def api_news():
    category = request.args.get("category", "all")
    limit = int(request.args.get("limit", 25))
    return jsonify(fetch_news(category=category, limit=limit))


@app.route("/api/news/full")
def api_news_full():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url required"}), 400
    data = fetch_article(url)
    if not data:
        return jsonify({"error": "failed to load article"}), 500
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)