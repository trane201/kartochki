"""Автотест сайта «Карточки» в демо-режиме (без Firebase).

Запуск из корня репозитория:
    pip install playwright && python -m playwright install chromium
    python tests/smoke_test.py

Тест поднимает локальный сервер, подменяет config.js на пустой (демо-режим),
создаёт набор и проходит основные режимы на ширине компьютера и iPhone.
Завершается с кодом 1, если что-то сломалось.
"""
import asyncio, os, subprocess, sys, time, json
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8799
URL = f"http://127.0.0.1:{PORT}/index.html"
CARDS = """丁=dīng — гвоздь
土=tǔ — земля
工=gōng — работа
上=shàng — подниматься; наверху // 上海 - Шанхай
王=wáng — государь
人=rén — человек
大=dà — большой
中国=zhōngguó — Китай
老师=lǎoshī — учитель"""
# озвучка и звуки - заглушки, чтобы тест не зависел от голосов в системе
STUB = """window.__said=[]; speechSynthesis.speak=u=>{window.__said.push(u.text); setTimeout(()=>u.onend&&u.onend(),30)}; speechSynthesis.cancel=()=>{};
window.SpeechRecognition=window.webkitSpeechRecognition=class{ start(){ setTimeout(()=>{ this.onresult&&this.onresult({results:[[{transcript:window.__heard||'人'}]]}); this.onend&&this.onend(); },50);} abort(){} };"""

problems = []
def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond: problems.append(msg)

async def finish_quiz(pg, limit=60):
    for _ in range(limit):
        if await pg.query_selector("#nx"):
            await pg.click("#nx"); await pg.wait_for_timeout(60); continue
        if await pg.query_selector(".opt:not([disabled])"):
            await pg.click(".opt >> nth=0"); await pg.wait_for_timeout(60); continue
        if await pg.query_selector("#ans"):
            await pg.fill("#ans", "x"); await pg.click("#chk"); await pg.wait_for_timeout(60); continue
        break

async def run(browser, name, viewport, mobile):
    ctx = await browser.new_context(viewport=viewport, has_touch=mobile, is_mobile=mobile)
    pg = await ctx.new_page(); errs = []
    await ctx.route("**/config.js", lambda r: r.fulfill(content_type="application/javascript", body="window.FIREBASE_CONFIG={};"))
    await pg.add_init_script(STUB)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    dlg = {"dismiss": False}   # True - следующий диалог отклонить («Отмена»)
    pg.on("dialog", lambda d: asyncio.ensure_future(d.dismiss() if dlg["dismiss"] else d.accept()))
    overflow = "document.documentElement.scrollWidth>window.innerWidth+1"

    await pg.goto(URL + "#/new"); await pg.wait_for_timeout(400)
    await pg.fill("#ti", "Тест"); await pg.fill("#fo", "Китайский")
    await pg.click("#cols button[data-c='3']"); await pg.fill("#tx", CARDS); await pg.wait_for_timeout(100)
    check("9 карточек" in await pg.inner_text("#ph"), f"[{name}] разбор списка карточек")
    await pg.click("#sv"); await pg.wait_for_timeout(500)
    sid = (await pg.evaluate("location.hash")).split("/")[2]
    modes = await pg.evaluate("[...document.querySelectorAll('.mode b')].map(x=>x.innerText)")
    check(all(m in modes for m in ["Повторение","Карточки","Тест","Ввод","Аудирование","Тоны","Подбор","Экзамен","Бесконечный"]), f"[{name}] все режимы на странице набора")

    for mode in ["cards", "test", "write", "listen", "tones", "speak", "match", "exam", "endless", "review"]:
        await pg.goto(URL + "#/"); await pg.goto(URL + f"#/study/{sid}/{mode}"); await pg.wait_for_timeout(400)
        check(not await pg.evaluate(overflow), f"[{name}] {mode}: ничего не вылезает за край")
        if await pg.query_selector("#go"):
            await pg.click("#go"); await pg.wait_for_timeout(300)
            check(not await pg.evaluate(overflow), f"[{name}] {mode}: вопрос помещается по ширине")
        if mode in ("test", "write", "listen", "tones"):
            if await pg.query_selector(".opt"):
                await pg.click(".opt >> nth=0")
            else:
                await pg.fill("#ans", "x"); await pg.click("#chk")
            await pg.wait_for_timeout(200)
            cls = await pg.evaluate("document.querySelector('#qp').className")
            check(("right" in cls or "wrong" in cls) and await pg.query_selector("#nx") is not None, f"[{name}] {mode}: подсветка ответа и кнопка «Далее»")
            await finish_quiz(pg)
            check(await pg.query_selector("#ag") is not None, f"[{name}] {mode}: экран результата с «Повторить»")
            await pg.click("#ag"); await pg.wait_for_timeout(300)
            check(await pg.query_selector("#qp") is not None, f"[{name}] {mode}: «Повторить» запускает тот же тренажёр")
        if mode == "exam":
            await finish_quiz(pg)
            if await pg.query_selector("#mg"):
                await pg.click("#mg"); await pg.wait_for_timeout(300)
                m = {c["t"]: c["d"] for c in await pg.evaluate(f"JSON.parse(localStorage.getItem('kartochki_demo_sets_v1'))['{sid}'].cards")}
                tiles = await pg.evaluate("[...document.querySelectorAll('.mt')].map(b=>b.innerText)")
                defs = {x: i for i, x in enumerate(tiles) if x not in m}
                for i, x in enumerate(tiles):
                    if x in m:
                        await pg.click(f".mt[data-k='{i}']"); await pg.click(f".mt[data-k='{defs[m[x]]}']"); await pg.wait_for_timeout(40)
                await pg.wait_for_timeout(800)
            check("Итог экзамена" in await pg.inner_text("main"), f"[{name}] экзамен доходит до итога")
        if mode == "endless":
            for _ in range(8):
                if await pg.query_selector(".opt"): await pg.click(".opt >> nth=0")
                else: await pg.fill("#ans", "x"); await pg.click("#chk")
                await pg.wait_for_timeout(60); await pg.click("#nx"); await pg.wait_for_timeout(60)
            await pg.click("#stop"); await pg.wait_for_timeout(300)
            check("итог" in (await pg.inner_text("main")).lower(), f"[{name}] бесконечный режим останавливается «Стоп»")

    await pg.goto(URL + f"#/set/{sid}"); await pg.wait_for_timeout(400)
    await pg.goto(URL + f"#/edit/{sid}"); await pg.wait_for_timeout(400)
    check("上海 - Шанхай" in await pg.input_value("#tx"), f"[{name}] заметка сохраняется и возвращается в редактор")

    # редактор предупреждает о несохранённых изменениях
    await pg.fill("#ti", "Тест изменён")
    dlg["dismiss"] = True
    await pg.evaluate("location.hash='#/'"); await pg.wait_for_timeout(300)
    dlg["dismiss"] = False
    check(await pg.query_selector("#tx") is not None and "edit" in await pg.evaluate("location.hash"), f"[{name}] редактор не закрывается без подтверждения, если есть изменения")
    await pg.goto(URL + "#/"); await pg.wait_for_timeout(300)   # теперь подтверждаем уход

    prog = f"JSON.parse(localStorage.getItem('kartochki_progress_v1')||'{{}}')['{sid}']||{{}}"
    # звёздочка и «знаю» сохраняются изменениями, сброс прогресса звёздочки не трогает
    await pg.goto(URL + f"#/set/{sid}"); await pg.wait_for_timeout(400)
    if not await pg.query_selector("#ctab .starb.on"):
        await pg.click("#ctab .starb >> nth=0"); await pg.wait_for_timeout(900)
    stars = len((await pg.evaluate(prog)).get("starred", []))
    check(stars >= 1, f"[{name}] звёздочка сохраняется")
    await pg.goto(URL + "#/"); await pg.goto(URL + f"#/set/{sid}"); await pg.wait_for_timeout(400)
    if await pg.query_selector("#rp"):
        await pg.click("#rp"); await pg.wait_for_timeout(500)
        p = await pg.evaluate(prog)
        check(len(p.get("starred", [])) == stars and not p.get("known"), f"[{name}] «Сбросить прогресс» сбрасывает «знаю», но оставляет звёздочки")

    # повторение: можно начинать с определения
    await pg.goto(URL + "#/"); await pg.goto(URL + f"#/study/{sid}/review"); await pg.wait_for_timeout(400)
    await pg.click("[data-o='revFront'][data-v='d']"); await pg.wait_for_timeout(200)
    await pg.click("#go"); await pg.wait_for_timeout(300)
    front = await pg.inner_text(".face.front")
    check(any(d in front for d in ["гвоздь","земля","работа","подниматься","государь","человек","большой","Китай","учитель"]), f"[{name}] повторение: сначала определение")
    await pg.evaluate("localStorage.setItem('kartochki_settings', JSON.stringify({...JSON.parse(localStorage.getItem('kartochki_settings')||'{}'), revFront:'t'}))")

    # ввод произношения не пиньинем (транскрипция): ерунда не засчитывается, правильный ответ - да
    await pg.goto(URL + "#/new"); await pg.wait_for_timeout(400)
    await pg.fill("#ti", "EN"); await pg.click("#cols button[data-c='3']")
    await pg.fill("#tx", "apple\t[ˈæpəl]\tяблоко\ndog\t[dɒɡ]\tсобака"); await pg.click("#sv"); await pg.wait_for_timeout(500)
    sid_en = (await pg.evaluate("location.hash")).split("/")[2]
    await pg.evaluate("localStorage.setItem('kartochki_write_opts2', JSON.stringify({n:'all',dir:'wtp',tonesReq:true}))")
    await pg.goto(URL + "#/"); await pg.goto(URL + f"#/study/{sid_en}/write"); await pg.wait_for_timeout(400)
    await pg.click("#go"); await pg.wait_for_timeout(300)
    await pg.fill("#ans", "абракадабра"); await pg.click("#chk"); await pg.wait_for_timeout(200)
    check("wrong" in await pg.evaluate("document.querySelector('#qp').className"), f"[{name}] транскрипция: неверный ответ не засчитывается")
    await pg.click("#nx"); await pg.wait_for_timeout(200)
    ans = "ˈæpəl" if "apple" in await pg.inner_text("#qp") else "dɒɡ"
    await pg.fill("#ans", ans); await pg.click("#chk"); await pg.wait_for_timeout(200)
    check("right" in await pg.evaluate("document.querySelector('#qp').className"), f"[{name}] транскрипция: верный ответ засчитывается")

    # статистика прибавляется, а не перезаписывается
    await pg.wait_for_timeout(2300)
    st = await pg.evaluate("Object.values(JSON.parse(localStorage.getItem('kartochki_stats_v1')||'{\"days\":{}}').days).reduce((a,d)=>a+d.n,0)")
    check(st >= 10, f"[{name}] статистика копит ответы ({st})")
    check(not errs, f"[{name}] нет ошибок JavaScript: {errs[:3]}")
    await ctx.close()

async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            chrome = os.environ.get("CHROME_PATH")
            browser = await p.chromium.launch(executable_path=chrome) if chrome else await p.chromium.launch()
            await run(browser, "компьютер", {"width": 1200, "height": 850}, False)
            await run(browser, "iPhone", {"width": 390, "height": 844}, True)
            await browser.close()
    finally:
        srv.terminate()
    print("\nИТОГ:", "всё в порядке" if not problems else f"проблем: {len(problems)}")
    sys.exit(1 if problems else 0)

if __name__ == "__main__":
    asyncio.run(main())
