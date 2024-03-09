#! -*-coding: utf8-*-
import random
import time

START = 2500

def generate_random_number(start, step, swing):
    global START
    choice_list = [0, step, (0 - step)]
    if start < START * (1 - swing):
        return start + 1
    if start > START * (1 + swing):
        return start - 1
    return start + random.choice(choice_list)

def create_index_data():
    swing = random.choice([0.01, 0.02, 0.03, 0.04, 0.05])
    random_number_list = []
    global START
    start = START
    print "start", start
    print "swing", swing
    for i in range(21600):
        start = generate_random_number(start, 1, swing)
        random_number_list.append(start)

    step_list = []
    for i in range(1, len(random_number_list)):
        step_list.append(random_number_list[i] - random_number_list[i - 1])

    index_list = []
    for i in range(len(step_list)):
        index_list.append((random_number_list[i], step_list[i]))
    print "max", max(random_number_list)
    print "min", min(random_number_list)
    return random_number_list

def test_strategy():
    market_data = create_index_data()
    #多 long
    #空 short
    direction = "long"
    num_loss = 0
    open_pos = market_data[0]
    peak_pos = market_data[0]
    latest_pos = 0
    close_gain_list = []
    for i in market_data[1:]:
        latest_pos = i
        if direction == "long" and latest_pos >= peak_pos:
            peak_pos = latest_pos
        if direction == "short" and latest_pos <= peak_pos:
            peak_pos = latest_pos
        #print "最新点位", latest_pos, "开仓点位", open_pos, "峰值点位", peak_pos
        if direction == "long":
            if (peak_pos - latest_pos) >= 3:
                #print "做多平仓", latest_pos - 1
                close_gain = latest_pos - 1 - open_pos
                #print "平仓收益", close_gain
                close_gain_list.append(close_gain)
                if close_gain <= 0:
                    num_loss += 1
                else:
                    num_loss = 0
                if num_loss >= 2:
                    if direction == "long":
                        direction = "short"
                        #print "开始做空", latest_pos - 1
                        open_pos = latest_pos - 1
                        peak_pos = latest_pos
                        num_loss = 0

                if direction == "long":
                    #print "做多开仓", latest_pos 
                    open_pos = latest_pos 
                    peak_pos = latest_pos

        if direction == "short":
            if (latest_pos - peak_pos) >= 3:
                #print "做空平仓", latest_pos + 1
                close_gain = open_pos - (latest_pos + 1)
                #print "平仓收益", close_gain
                close_gain_list.append(close_gain)
                if close_gain <= 0:
                    num_loss += 1
                else:
                    num_loss = 0
                if num_loss >= 2:
                    if direction == "short":
                        direction = "long"
                        #print "开始做多", latest_pos + 1
                        open_pos = latest_pos + 1
                        peak_pos = latest_pos
                        num_loss = 0

                if direction == "short":
                    #print "做空开仓", latest_pos 
                    open_pos = latest_pos 
                    peak_pos = latest_pos

        #time.sleep(1)
        #print
    print "平仓收益总和", sum(close_gain_list)
    print

for i in range(10):
    test_strategy()
