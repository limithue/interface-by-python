from fastapi import FastAPI

# 创建应用实例
app = FastAPI(title="My Python API")

@app.get("/")
def read_root():
    """
    根路径接口
    """
    return {"message": "Hello, World! API is running."}

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    """
    获取特定 Item 的接口示例
    """
    return {"item_id": item_id, "query": q}

# 这里的代码只有在直接运行 python main.py 时才会执行
if __name__ == "__main__":
    import uvicorn
    # 启动服务器，开启自动重载（修改代码自动重启）
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
