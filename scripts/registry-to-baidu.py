import lxml.etree
import requests
import os

host_name = "www.wangsaiyu.com"
sitemap_path = "public/sitemap.xml"

tree = lxml.etree.parse(sitemap_path)

namespaces = {
    'sitemapindex': 'http://www.sitemaps.org/schemas/sitemap/0.9',
}

urls = ""
for url in tree.xpath("//sitemapindex:loc/text()", namespaces=namespaces):
    urls += url.strip() + '\n'

headers = {
    'User-Agent': 'curl/7.12.1',
    'Host': 'data.zz.baidu.com',
    'Content-Type': 'text/plain',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Content-Length': str(len(urls))
}

api_path = "http://data.zz.baidu.com/urls?site=https://www.wangsaiyu.com&token={}".format(os.getenv("BAIDU_TOKEN"))
res = requests.post(api_path, headers=headers, data=urls)

print(res.text)
