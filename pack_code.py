import os

ignore_dirs = {'venv', '.git', '__pycache__', 'node_modules', '.idea', 'output'}
ignore_exts = {'.pyc', '.log', '.csv', '.zip'}

with open('repo_context.txt', 'w', encoding='utf-8') as out:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for file in files:
            if any(file.endswith(ext) for ext in ignore_exts): continue
            filepath = os.path.join(root, file)
            out.write(f"\n{'='*20} {filepath} {'='*20}\n")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"[无法读取: {e}]")
print("打包完成！请发送 repo_context.txt")
