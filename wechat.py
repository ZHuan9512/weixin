from urllib.parse import urlencode
from requests.exceptions import ConnectionError
import requests
import pymongo
from pyquery import PyQuery as pq
from config import *
import re
base_url = 'https://weixin.sogou.com/weixin?'
header = {
    'Cookie': 'sw_uuid=8222458958; sg_uuid=6309065996; dt_ssuid=2372241637; pex=C864C03270DED3DD8A06887A372DA219231FFAC25A9D64AE09E82AED12E416AC; ssuid=2346357050; IPLOC=CN4401; SUID=4391BFAF2313940A000000005BA4A6AC; CXID=D04C4871320DB1160D021882AD085077; wuid=AAGNyJzFIgAAAAqLK1dg8QMAGwY=; SUV=00AA174AAFBF92CD5BA9BC4CA9FA7421; ad=Lkllllllll2bESbBlllllVsHVH6lllllN7q3Plllll9lllllRCxlw@@@@@@@@@@@; ABTEST=8|1543503090|v1; weixinIndexVisited=1; SNUID=0BC54AF98F8BF4405DAE1F188F5EFAF6; sct=2; JSESSIONID=aaaHr-EIijDmT7Xfnz6Cw; ppinf=5|1543542827|1544752427|dHJ1c3Q6MToxfGNsaWVudGlkOjQ6MjAxN3x1bmlxbmFtZTo3MjolRTglODIlOUElRTUlQUQlOTAlRTYlOUMlODklRTglODclQUElRTUlQjclQjElRTclOUElODQlRTYlODMlQjMlRTYlQjMlOTV8Y3J0OjEwOjE1NDM1NDI4Mjd8cmVmbmljazo3MjolRTglODIlOUElRTUlQUQlOTAlRTYlOUMlODklRTglODclQUElRTUlQjclQjElRTclOUElODQlRTYlODMlQjMlRTYlQjMlOTV8dXNlcmlkOjQ0Om85dDJsdUNKemFidDJxZnBubEhZN1lxQ3RIMWtAd2VpeGluLnNvaHUuY29tfA; pprdig=MTvluI_5DK5nKA0E2G0wOOwmTPpFRa3LVC45Xx6hTQiQAXVnBWHEJ_ukvEIRtkRI1BHnNbpBJtwd5zxyCIcD7Bpdp7RWuvFi-vLc4x4tFKEc6MC-y71eo12557wZ378XmTsQvOQrgweWgUSJ4yEjQ_Np7Njtb7USFMANBwa58Rs; sgid=26-38147945-AVwAmCsnliczHGtE9xJnmdHU',
    'Host': 'weixin.sogou.com',
    'Referer': 'https://open.weixin.qq.com/connect/qrconnect?appid=wx6634d697e8cc0a29&scope=snsapi_login&response_type=code&redirect_uri=https%3A%2F%2Faccount.sogou.com%2Fconnect%2Fcallback%2Fweixin&state=20151282-b38f-4803-9c85-1202efbf733c&href=https%3A%2F%2Fdlweb.sogoucdn.com%2Fweixin%2Fcss%2Fweixin_join.min.css%3Fv%3D20170315',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.110 Safari/537.36'
}
#初始代理为None
proxy = None
#设置最大出错数
max_count = 5


client = pymongo.MongoClient(MONGO_URI)
db = client[MONGO_DB]

#获取代理
def get_proxy():
    try:
        response = requests.get(PROXY_POOL_URL)
        if response.status_code == 200:
            return response.text
        return None
    except ConnectionError:
        return None

#获取网页源代码
def get_html(url,count=1):
    print("Crawling",url)
    print("Trying Count",count)
    global proxy
    if count >= max_count:
        print("请求次数达到上限")
        return None
    try:
        if proxy:
            proxies = {
                'http':'http://' + proxy
            }
            response = requests.get(url,allow_redirects=False,headers=header,proxies=proxies)
        else:
            response = requests.get(url,allow_redirects=False, headers=header)
        if response.status_code == 200:
            return response.text
        if response.status_code == 302:
            #proxy
            print('302')
            proxy = get_proxy()
            if proxy:
                print("Using Proxy",proxy)
                return get_html(url)
            else:
                print("Get Proxy False")
                return None
    except ConnectionError as e:
        print("Error Occurred",e.args)
        proxy = get_proxy()
        count += 1
        return get_html(url,count)

def get_index(keyword,page):
    data = {
        'query': keyword,
        'type': 2,
        'page': page
    }
    queries = urlencode(data)
    url = base_url + queries
    html = get_html(url)
    return html

#解析索引页
def parse_index(html):
    doc = pq(html)
    items = doc('.news-box .news-list li .txt-box h3 a').items()
    for item in items:
        yield item.attr('href')

#获取详情页
def get_detail(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        return None
    except ConnectionError:
        return None

#解析详情页
def parse_detail(html):
    doc = pq(html)
    title = doc('.rich_media_title').text()
    content = doc('.rich_media_content p').text()
    #文章发布时间用pyquery提取为空，所以改用正则匹配文章发布时间
    pattern = re.compile('var publish_time = "(.*?)"',re.S)
    time = re.search(pattern,html)
    date = time.group(1)
    nickname = doc('#js_profile_qrcode > div > strong').text()
    wechat = doc('#js_profile_qrcode > div > p:nth-child(3) > span').text()
    return {
        'title':title,
        'date': date,
        'content':content,
        'nickname':nickname,
        'wechat':wechat
    }

#保存到MONGODB
def save_to_mongo(data):
    if db['articles'].update({'title':data['title']},{'$set':data},True):
        print("Save To Mongo",data['title'])
    else:
        print("Save To Monge Failed",data['title'])

def main():
    for page in range(1,101):
        html = get_index(KEYWORD,page)
        if html:
            article_urls = parse_index(html)
            for article_url in article_urls:
                article_html = get_detail(article_url)
                if article_html:
                    article_data = parse_detail(article_html)
                    print(article_data)
                    save_to_mongo(article_data)


if __name__ == '__main__':
    main()
