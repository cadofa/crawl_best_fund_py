# -*- coding: utf-8 -*-

import requests

url = "http://hq.sinajs.cn/rn=iw6pa&list=nf_MA0,nf_MA2106,nf_MA2107,nf_MA2108,nf_MA2109,nf_MA2110,nf_MA2111,nf_MA2112,nf_MA2201,nf_MA2202,nf_MA2203,nf_MA2204,nf_MA2205"

def crawl_data():
    res = requests.get(url)
    res = res.text
    data_x = list()
    data_y = list()
    for r in res.split("\n")[1:-1]:
        line = r.split("=")[1]
        data_x.append(line.split(",")[0].replace('"',""))
        data_y.append(int(float(line.split(",")[8])))

    #data_x = [d.replace(u"甲醇", "MA") for d in data_x]

    return data_x, data_y


if __name__ == "__main__":
    crawl_data()
