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

TEST_COUNT = 51


tick_data_list = []
tick_mean = 0
mean_deviation = 0
high_sell_devs = [3,5,8,13,21,34,55,89]
low_buy_devs = [-3,-5,-8,-13,-21,-34,-55,-89]
buy_position_list = {}
sell_position_list = {}
close_profit_loss = 0
total_profit_loss = 0
oper_count = 0


def onTick(tick):
    global tick_data_list, tick_mean, mean_deviation, close_profit_loss, oper_count
    #print
    #print "行情数据-------------------*----------------------",  tick
    tick_data_list.append(tick)
    tick_mean = np.mean(tick_data_list)
    mean_deviation = int((tick - tick_mean)/tick_mean*1000)
    #开仓多单
    if mean_deviation in low_buy_devs:
        if mean_deviation not in buy_position_list.keys():
            buy_position_list.update({mean_deviation:tick})
    #开仓空单
    if mean_deviation in high_sell_devs:
        if mean_deviation not in sell_position_list.keys():
            sell_position_list.update({mean_deviation:tick})

    #print "行情",tick_data_list[-1]
    #print "均值",tick_mean
    #print "偏差",mean_deviation
    #if buy_position_list:
    #    print "**********多单持仓", buy_position_list
    #if sell_position_list:
    #    print "**********空单持仓", sell_position_list
    #if close_profit_loss:
    #    print "*********平仓盈亏", close_profit_loss
    #平仓
    if mean_deviation == 0:
        if buy_position_list:
        #平仓多单
            for k,v in buy_position_list.items():
                #print "当前价格", tick
                #print "平仓多单", v
                #print "平仓盈亏", (tick - 1) - v
                close_profit_loss += (tick - 1) - v
                oper_count += 1
            buy_position_list.clear()

        if sell_position_list:
            for k,v in sell_position_list.items():
                #print "当前价格", tick
                #print "平仓空单", v
                #print "平仓盈亏", v - (tick + 1)
                close_profit_loss += v - (tick + 1)
                oper_count += 1
            sell_position_list.clear()
        
    #time.sleep(2)

def test_strategy():
    market_data = create_index_data()
    for i in market_data:
        onTick(i)
        

prof_loss_list = []
win_prof_loss_list = []
for i in range(1, TEST_COUNT):
    fut_data = test_strategy()

    print "收盘", tick_data_list[-1]
    save_close_price(tick_data_list[-1])
    print "均价", tick_mean
    print "空单持仓", sell_position_list
    for k,v in sell_position_list.items():
        close_profit_loss += v - (tick_data_list[-1] + 1)
        oper_count += 1
    sell_position_list.clear()
    print "多单持仓", buy_position_list
    for k,v in buy_position_list.items():
        close_profit_loss += (tick_data_list[-1] - 1) - v
        oper_count += 1
    buy_position_list.clear()
    tick_data_list = []
    tick_mean = 0
    mean_deviation = 0
    print "平仓盈亏", close_profit_loss
    print "操作次数", oper_count
    prof_loss_list.append(close_profit_loss)
    total_profit_loss += close_profit_loss
    close_profit_loss = 0
    oper_count = 0
    print
    print

win_prof_loss_list = [p for p in prof_loss_list if p>0]
print "盈亏列表", prof_loss_list, len(prof_loss_list)
print "累计平仓盈亏", total_profit_loss
print "盈利列表", win_prof_loss_list, len(win_prof_loss_list)
print "胜率", float(len(win_prof_loss_list))/len(prof_loss_list)*100
