from django.http import HttpResponse
from django.shortcuts import render
from crawl_future_data import crawl_data

import random

def index(request):
    data_x, data_y = crawl_data()
    for i in range(len(data_x)):
        print data_x[i], data_y[i]
    return render(request, 'line-simple.html', {"data_x": data_x, 
                                                "data_y": data_y})
