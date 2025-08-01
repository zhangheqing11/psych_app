# gunicorn.conf.py
# 增加超时时间以允许较长的AI API请求

# 将超时时间设置为300秒（5分钟）
# 默认值是30秒
timeout = 300

# 增加worker数量可以提高并发处理能力，对于免费套餐，2-3个通常是合理的
workers = 3
