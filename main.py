from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, render_template
import requests
from scrapy.crawler import CrawlerRunner
from scrapy.utils.project import get_project_settings
from twisted.internet import reactor
from azure.storage.blob import BlobServiceClient
import string
import os
import scrapy
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
executor = ThreadPoolExecutor(1)
API_URL = "https://api-inference.huggingface.co/models/soleimanian/financial-roberta-large-sentiment"
HEADERS = {"Authorization": "Bearer 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"}
@app.route('/')
def index():
    return render_template('index.html')

def query(payload):
    response = requests.post(API_URL, headers=HEADERS, json=payload)
    return response.json()


class MainSpider(scrapy.Spider):
    name = 'main_spider'
    start_urls = []
    combined_content = []

    class MainSpider(scrapy.Spider):
        name = 'main_spider'
        start_urls = []
        combined_content = []

        def parse(self,response):
            main_content = response.xpath('//text()').getall()
            self.combined_content.extend(main_content)
            for link in response.xpath('//a'):
                link_text = link.xpath('.//text()').get()
                link_url = link.xpath('.//@href').get()

                if link_text and link_url:
                    hyperlink_info = f'Hyperlink: {link_text.strip()}: {link_url.strip()}'
                    self.combined_content.append(hyperlink_info)
                    yield response.follow(link_url, callback=self.parse_hyperlink_content)

        def parse_hyperlink_content(self, response):
            link_text = response.xpath('//title/text()').get()
            link_content = response.xpath('//text()').getall()

            self.combined_content.append(f'----- Hyperlink Content: {link_text} -----\n')
            self.combined_content.extend(link_content)


def get_valid_filename(name):
    valid_chars = '-_.() %s%s' % (string.ascii_letters, string.digits)
    return ''.join(c if c in valid_chars else '_' for c in name)


def generate_container_name(user_id):
    return f'user-container-{user_id}'


def create_container(connection_string, container_name):
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)

    try:
        container_client.create_container()
        print(f"Container '{container_name}' created successfully.")
    except Exception as e:
        print(f"Error creating container '{container_name}': {e}")


@app.route('/hello', methods=['GET'])
def hello():
    return "Hello, World!"


@app.route('/analyze_sentiment', methods=['POST'])
def analyze_sentiment():
    data = request.get_json()
    text = data.get('text')

    if text is None:
        return jsonify({"error": "Text not provided"}), 400

    payload = {"inputs": [text]}
    output = query(payload)

    print("Output:", output)

    highest_overall_sentiment = max(output[0], key=lambda x: x["score"])
    highest_label = highest_overall_sentiment["label"]
    highest_score = highest_overall_sentiment["score"]

    result = {
        "text": text,
        "highest_sentiment": highest_label,
        "highest_score": highest_score
    }

    return jsonify(result), 200


@app.route('/urldata', methods=['POST'])
def scrape():
    data = request.get_json()
    url = data.get('url')
    user_id = data.get('user_id')

    if not url:
        return jsonify({"error": "URL not provided"}), 400
    if not user_id:
        return jsonify({"error": "User ID not provided"}), 400

    try:
        container_name = generate_container_name(user_id)

        blob_service_client = BlobServiceClient.from_connection_string(
            "DefaultEndpointsProtocol=https;AccountName=autodemo;AccountKey=vv3+LSjLsvivd2lzKpv2CMlCyBKDmB0dPvB7wtWAKpRWD3NUMwXeCfj7saZojzGg/TkMp6WR+Fql+AStYHqTIg==;EndpointSuffix=core.windows.net")
        blob_name = get_valid_filename(url) + ".txt"

        container_client = blob_service_client.get_container_client(container_name)
        if not container_client.exists():
            create_container(
                "DefaultEndpointsProtocol=https;AccountName=autodemo;AccountKey=vv3+LSjLsvivd2lzKpv2CMlCyBKDmB0dPvB7wtWAKpRWD3NUMwXeCfj7saZojzGg/TkMp6WR+Fql+AStYHqTIg==;EndpointSuffix=core.windows.net",
                container_name)

        def run_crawler():
            runner = CrawlerRunner(get_project_settings())
            deferred = runner.crawl(MainSpider, start_urls=[url])
            deferred.addBoth(lambda _: reactor.stop())
            reactor.run()

            output_filename = blob_name
            with open(output_filename, 'w', encoding='utf-8') as output_file:
                output_file.write("\n".join(MainSpider.combined_content))

            blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
            with open(output_filename, 'rb') as file:
                blob_client.upload_blob(file)
            os.remove(output_filename)

        # Execute the crawler in a background thread
        executor.submit(run_crawler)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "Scraping process completed and file uploaded"}), 200


if __name__ == '__main__':
    app.run()
