"""Exact reviewed headline corrections and bounded terminology checks.

Corrections apply only to identical source titles, never to similar events.
"""
import re

REVIEWED = {
 '台海緊張能緩解？陸媒指陸美安全對話釋「穩定訊號」': 'Can Taiwan Strait tensions ease? Chinese media says China–US security dialogue sends a signal of stability',
 '中國出動17機艦擾台 國軍嚴密監控應處': 'China deploys 17 aircraft and vessels around Taiwan; Taiwan military closely monitors and responds',
 '沖繩變天牽動台海防線 高市陣營拿下關鍵勝利': 'Political shift in Okinawa affects Taiwan Strait defenses as Takaichi camp wins a key victory',
 '美智庫警告華府「勿介入台海衝突」 風險遠超潛在利益輿論：賴「倚美謀獨」推台灣入火坑- 中國': 'US think tank warns Washington not to intervene in a Taiwan Strait conflict, saying risks far outweigh potential benefits; commentary accuses Lai of endangering Taiwan by relying on the US to seek independence — China',
 '台海響警號｜未開戰先動員 中國修例10.1「平戰快速轉換」 可徵收民企晶片': 'Taiwan Strait alarm: mobilization before war; China’s legal amendment for rapid peacetime-to-wartime transition on 10.1 allows requisitioning private firms’ chips',
 'MQ-9B首度升空 專家：打造台海「偵搜牆」': 'MQ-9B takes its first flight; expert says it will create a surveillance wall in the Taiwan Strait',
 '台海監偵「千里眼」升空！ MQ-9B首度在花蓮試飛｜#鏡新聞': 'Taiwan Strait surveillance aircraft takes flight: MQ-9B makes its first test flight in Hualien | Mirror News',
 '台海監偵「千里眼」升空！　MQ-9B首度在花蓮試飛': 'Taiwan Strait surveillance aircraft takes flight: MQ-9B makes its first test flight in Hualien',
 '陸委會：台將與美深化合作 共同維護台海現狀': 'Mainland Affairs Council: Taiwan will deepen cooperation with the US to jointly maintain the Taiwan Strait status quo',
 '台海今年無大型軍演美中都要管控衝突| 軍事 | 要聞': 'No large-scale military exercises in the Taiwan Strait this year; both the US and China seek to manage conflict | Military | Top news',
 '自由開講》日本看台海是國家利益 南韓仍「事大」思維？': 'Opinion: Japan sees the Taiwan Strait as a national interest; does South Korea still defer to major powers?',
 '沖繩12年來首見保守派知事日本強化台海周邊防衛添助力| 國際': 'Okinawa elects its first conservative governor in 12 years, aiding Japan’s efforts to strengthen defenses around the Taiwan Strait | International',
}


def valid_english(source, value):
    if not isinstance(value, str) or not re.search(r'[A-Za-z]', value) or re.search(r'[\u3400-\u9fff]', value):
        return False
    low = value.lower()
    if '機艦' in source and not any(s in source for s in ('航母', '航空母艦')) and 'aircraft carrier' in low:
        return False
    if '陸委會' in source and 'mainland affairs council' not in low:
        return False
    if '高市' in source and 'takaichi' not in low:
        return False
    if '沖繩變天' in source and 'weather' in low:
        return False
    return True
