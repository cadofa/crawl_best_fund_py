#! -*-coding: utf8-*-

import random
import pickle

SAMPLE_SIZE = 3600 * 2

def get_close_price():
    try:
        with open('close.pk', 'rb') as file:
            close = pickle.load(file)
        return close
    except IOError, e:
        return 2500

def generate_random_number(start, m_data, step, swing):
    choice_list = [0, step, (0 - step)]
    if m_data < start * (1 - swing):
        return m_data + 1
    if m_data > start * (1 + swing):
        return m_data - 1
    if m_data < 2000:
        return m_data + 1
    if m_data > 3500:
        return m_data - 1
    return m_data + random.choice(choice_list)

def create_index_data():
    swing = random.choice([0.003, 0.004, 0.005, 0.005, 0.008, 0.008, 0.013, 0.013, 0.021, 0.034, 0.055])
    random_number_list = []
    start = get_close_price() + random.choice([0, -3,-5,-8,-13,3,5,8,13])
    m_data = start
    print "开盘价", m_data
    print "日内振幅", swing
    for i in range(SAMPLE_SIZE):
        m_data = generate_random_number(start, m_data, 1, swing)
        random_number_list.append(m_data)

    step_list = []
    for i in range(1, len(random_number_list)):
        step_list.append(random_number_list[i] - random_number_list[i - 1])

    index_list = []
    for i in range(len(step_list)):
        index_list.append((random_number_list[i], step_list[i]))
    print "最高价", max(random_number_list)
    print "最低价", min(random_number_list)
    return random_number_list
