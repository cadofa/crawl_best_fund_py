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

worm_config = [
        {
            "worm_list": [],
            "worm_length": 900,
            "worm_mean_list":[],
            #蠕虫均值观察周期
            "obser_period": 180,
            #开仓点位方向
            "position": [],
            #平仓收益
            "close_gain": 0,
            "oper_count": 0
        },
    ]

def onTick(tick):
    global worm_config
    #print
    #print "行情数据-------------------*----------------------",  tick
    for w in worm_config:
        w["worm_list"].append(tick)
        if len(w["worm_list"]) > w["worm_length"]:
            w["worm_list"].pop(0)

        if len(w["worm_mean_list"]) > w["obser_period"] - 1:
            w["worm_mean_list"].pop(0)

        if len(w["worm_list"]) < w["worm_length"]:
            #print "蠕虫长度", len(w["worm_list"])
            continue
        else:
            worm_max = max(w["worm_list"])
            worm_min = min(w["worm_list"])
            worm_mean = np.mean(w["worm_list"])
            w["worm_mean_list"].append(worm_mean)
            #print "蠕虫",  len(w["worm_list"])
            #print "蠕虫均值", len(w["worm_mean_list"])
            if len(w["worm_mean_list"]) >= w["obser_period"]:
                if w["worm_mean_list"][-1] > w["worm_mean_list"][0]:
                    #print "多头↑↑↑↑涨涨涨涨趋势"
                    if not w["position"]:
                        #print "多头建仓", tick
                        w["position"].append((tick, "B"))
                    if w["position"][0][-1] == "S":
                        print "空单开仓点位", w["position"][0][0]
                        print "空单平仓点位", tick
                        print "空单平仓收益", w["position"][0][0] - tick
                        print
                        w["close_gain"] += (w["position"][0][0] - tick)
                        w["oper_count"] += 1
                        w["position"].remove(w["position"][-1])
                        continue
                if w["worm_mean_list"][-1] < w["worm_mean_list"][0]:
                    #print "空头↓↓↓↓跌跌跌跌趋势"
                    if not w["position"]:
                        #print "空头建仓", tick
                        w["position"].append((tick, "S"))
                        continue
                    if w["position"][0][-1] == "B":
                        print "多单开仓点位", w["position"][0][0]
                        print "多单平仓点位", tick
                        print "多单平仓收益", tick - w["position"][0][0]
                        print
                        w["close_gain"] += (tick - w["position"][0][0])
                        w["oper_count"] += 1
                        w["position"].remove(w["position"][-1])
                        continue

    #time.sleep(2)

def test_strategy():
    global worm_config
    market_data = create_index_data()
    position_list = []
    operation_stack = []
    x_c = 0
    for i in market_data:
        onTick(i)
        
    print worm_config[0]["close_gain"], worm_config[0]["oper_count"]
    print

for i in range(1, TEST_COUNT):
    fut_data = test_strategy()
    #time.sleep(2)
         
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
#    position_list = []
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
