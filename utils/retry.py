import time
import functools

def retry_with_fallback(max_retries=3, delay=2, backoff=2):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    print(f"⚠️ [{func.__name__}] 触发重试 (第 {attempt + 1}/{max_retries} 次) 异常: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(delay * (backoff ** attempt))
            
            print(f"❌ [{func.__name__}] {max_retries} 次尝试全部失败。")
            raise last_exception
        return wrapper
    return decorator