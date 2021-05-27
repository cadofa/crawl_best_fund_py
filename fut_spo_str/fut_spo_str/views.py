from django.http import HttpResponse
from django.shortcuts import render
from crawl_future_data import crawl_data

import random

def index(request):
    data_x, data_y = crawl_data()
    return render(request, 'line-simple.html', {"data_x": data_x, 
                                                "data_y": data_y})
