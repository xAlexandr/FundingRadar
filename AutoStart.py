import asyncio
import subprocess
import os
import signal
import aiohttp

DEBUG = os.getenv('DEBUG', 'False') == 'True'
ORIGIN = os.getenv('ORIGIN')


GUNICORN_CMD = [
    "daphne",
    "-b", "0.0.0.0",
    "-p", "8000",
    "--verbosity", "0",
    "funding_web.asgi:application"
]


SEARCH_CMD = ["python3", "./trading/search.py"]

if DEBUG:
    CHECK_URL = "http://0.0.0.0:8000/api/coins/"
else:
    CHECK_URL = f"{ORIGIN}/api/coins/"

gunicorn_process = None
search_process = None
shutdown_event = asyncio.Event()
process_lock = asyncio.Lock()
shutting_down = False  # Флаг завершения

def safe_kill(process):
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except ProcessLookupError:
        pass

def check_process_running(process):
    return process is not None and process.poll() is None

async def start_processes():
    global gunicorn_process, search_process
    # print("🚀 Запуск search.py...")
    # search_process = subprocess.Popen(
    #     SEARCH_CMD,
    #     preexec_fn=os.setsid,
    #     env=os.environ.copy()
    # )
    # await asyncio.sleep(2)

    print("🚀 Запуск Gunicorn...")
    gunicorn_process = subprocess.Popen(
        GUNICORN_CMD,
        preexec_fn=os.setsid,
        env=os.environ.copy()
    )
    await asyncio.sleep(2)

async def check_server():
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(CHECK_URL, timeout=5) as response:
                if response.status in (200, 401):
                  #  print("✅ Сервер работает")
                    return True
                print(f"⚠️ Сервер ответил кодом: {response.status}")
                return False
        except aiohttp.ClientError:
            print("❌ Сервер не отвечает!")
            return False

def restart_process(cmd, name):
    print(f"🔄 Перезапуск {name}...")
    return subprocess.Popen(
        cmd,
        preexec_fn=os.setsid,
        env=os.environ.copy()
    )

async def monitor():
    global gunicorn_process, search_process, shutting_down

    while not shutting_down:
        await asyncio.sleep(30)
      #  print("\n🔍 Проверка состояния процессов")

        async with process_lock:
            if shutting_down:
                break

            if not await check_server():
                print("⚠️ Перезапуск Gunicorn (сервер недоступен)")
                safe_kill(gunicorn_process)
                await asyncio.sleep(1)
                gunicorn_process = restart_process(GUNICORN_CMD, "Gunicorn")

            # if not check_process_running(search_process):
            #     print("⚠️ search.py упал, перезапускаем...")
            #     safe_kill(search_process)
            #     await asyncio.sleep(1)
            #     search_process = restart_process(SEARCH_CMD, "search.py")

async def graceful_shutdown():
    global gunicorn_process, search_process
    print("\n🛑 Завершение процессов...")

    async with process_lock:
        if gunicorn_process:
            print("⛔ Завершаем Gunicorn...")
            safe_kill(gunicorn_process)

        if search_process:
            print("⛔ Завершаем search.py...")
            safe_kill(search_process)

    await asyncio.sleep(1)
    print("✅ Все процессы завершены")

def shutdown_handler():
    global shutting_down
    if not shutting_down:
        print("\n📴 Получен сигнал завершения. Ожидаем остановки...")
        shutting_down = True
        shutdown_event.set()

async def main():
    await start_processes()
    monitor_task = asyncio.create_task(monitor())
    await shutdown_event.wait()
    monitor_task.cancel()
    await graceful_shutdown()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
