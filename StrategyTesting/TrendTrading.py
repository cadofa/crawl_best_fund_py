#! -*-coding: utf8-*-
import random
import time
import pickle
import matplotlib as mpl
mpl.use('Agg')
import numpy as np
import matplotlib.pyplot as plt
from utils import generate_random_number, create_index_data, get_close_price


def save_close_price(close):
    with open('close.pk', 'wb') as file:
        pickle.dump(close, file)

TEST_COUNT = 2


tick_data_list = []
tick_mean = 0

trend_config = [
    {
        "obser_period": 21,
        "mean_list": [],
        "tick_list": [],
        "position": [],
        "peak_value": 0,
        "close_gain": 0,
    },
]

def onTick(tick):
    global trend_config, tick_data_list, tick_mean
    #print
    #print "行情数据-------------------*----------------------",  tick
    tick_data_list.append(tick)
    tick_mean = np.mean(tick_data_list)
    for t in trend_config:
        #print "持仓数据", t["position"]
        #print "持仓参照峰值", t["peak_value"]
        t["tick_list"].append(tick)
        if len(t["tick_list"]) > t["obser_period"]:
            t["tick_list"].pop(0)
        t["mean_list"].append(tick_mean)
        if len(t["mean_list"]) > t["obser_period"]:
            t["mean_list"].pop(0)
        #print t["tick_list"]
        #print t["mean_list"]
        
        if (t['tick_list'][0] > t['mean_list'][0] 
            and t["tick_list"][1] < t["mean_list"][1] and tick < tick_mean):
            if not t["position"]:
                #print "下穿均线做空"
                #print "空单开仓", tick - 1, "S"
                t["position"].append((tick - 1, "S"))
                t["peak_value"] = tick - 1
        if (t['tick_list'][0] < t['mean_list'][0] 
            and t["tick_list"][1] > t["mean_list"][1] and tick > tick_mean):
            if not t["position"]:
                #print "上穿均线做多"
                #print "多单开仓", tick + 1, "B"
                t["position"].append((tick + 1, "B"))
                t["peak_value"] = tick + 1
        if t["position"]:
            if t["position"][0][1] == "B" and tick > t["peak_value"]:
                t["peak_value"] = tick
            if t["position"][0][1] == "S" and tick < t["peak_value"]:
                t["peak_value"] = tick
            if t["position"][0][1] == "B" and (t["peak_value"] - tick) >= t["obser_period"]:
                #print "多单平仓", tick - 1
                t["close_gain"] += (tick - 1) - t["position"][0][0]
                t["peak_value"] = 0
                t["position"].remove(t["position"][-1])
                continue
            if t["position"][0][1] == "S" and (tick - t["peak_value"]) >= t["obser_period"]:
                #print "空单平仓", tick + 1
                t["close_gain"] += t["position"][0][0] - (tick + 1)
                t["peak_value"] = 0
                t["position"].remove(t["position"][-1])
                continue

        
    #time.sleep(2)

def test_strategy():
    market_data = create_index_data()
    for i in market_data:
        onTick(i)
        

for i in range(1, TEST_COUNT):
    fut_data = test_strategy()
    #time.sleep(2)
    print trend_config 
         
#    ypoints = np.array(fut_data)
#    plt.plot(ypoints)
#    #print "操作记录", operation_stack
#    for i in operation_stack:
#        if operation_stack[-1][2] == "B":
#            plt.annotate("B", [i[0], i[1]], color="red")
#        if operation_stack[-1][2] == "S":
#            plt.annotate("S", [i[0], i[1]], color="green")
#    plt.text(118, max(fut_data), str(profit_loss), fontsize=12)
#    plt.savefig(image_name)
#    plt.close()
#    
#    operation_stack = []
#    profit_loss = {'profit_loss_position': 0, 'profit_loss_close': 0}

#print "历史盈亏列表", profit_loss_sum, len(profit_loss_sum)
#total_profit_loss = 0
#total_profit_loss_list = []
#for i in profit_loss_sum:
#    total_profit_loss += i
#    total_profit_loss_list.append(total_profit_loss)
#print "累计盈亏列表", total_profit_loss_list
#print "最大亏损", min(profit_loss_sum)
#print "最大盈利", max(profit_loss_sum)
#print "亏损次数", len([i for i in profit_loss_sum if i < 0])
#win_count =  len([i for i in profit_loss_sum if i > 0])
#print "盈利次数", win_count
#print "总体胜率", float(win_count)/len(profit_loss_sum)
#print "多次累计盈亏总和", sum(profit_loss_sum)
#
#total_profit = np.array(total_profit_loss_list)
#plt.plot(total_profit)
#plt.savefig("image/YieldCurve.png")
#plt.close()
