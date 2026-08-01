import os
import random
import asyncio
import discord
from discord import app_commands
import aiohttp
import os
from dotenv import load_dotenv


# .env 파일 로드
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ================= [필수 설정] =================
GUILD_ID = 1522917243498004550 
ROLE_ID = 1532959909128437890   
NOTIFICATION_CHANNEL_ID = 1531039903490642052
COMMENT_API_URL = "https://api-community.plaync.com/aion2/board/server_ko/article/6a6d64776276ae76f3e49a8a/comment/search/moreComment?moreSize=20&moreDirection=BEFORE&previousCommentId=0&orderType=desc"
BOARD_URL = "https://aion2.plaync.com/ko-kr/board/server/view?articleId=6a6d64776276ae76f3e49a8a"
# ===============================================

intents = discord.Intents.all()

class VerificationClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        # 슬래시 명령어 관리 트리를 초기화합니다.
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 지정된 서버(GUILD_ID)에 슬래시 명령어를 즉시 동기화합니다.
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

client = VerificationClient()

# 인증 대기 유저 목록: { user_id: "인증코드" }
pending_verifications = {}


@client.event
async def on_ready():
    print(f"==========================================")
    print(f" 봇 로그인 완료: {client.user.name}")
    print(f" 댓글 API 감시 루프를 시작합니다...")
    print(f"==========================================")
    
    # 봇 준비 완료 시 감시 루프 실행
    client.loop.create_task(check_comments_api_loop())


# 슬래시 명령어 (/인증) 등록
@client.tree.command(name="인증", description="게시판 댓글 인증 코드를 발급합니다.")
async def verify_command(interaction: discord.Interaction):
    code = str(random.randint(100000, 999999))
    pending_verifications[interaction.user.id] = code
    print(f"🔑 [{interaction.user.display_name}] 님 인증코드 발급: {code}")

    # 임베드(Embed) 상자 구성
    embed = discord.Embed(
        title="🔗 게시판 댓글 인증 안내",
        description="아래 게시글로 이동하여 발급된 인증코드를 댓글로 작성해 주세요!",
        color=0x3498DB # 깔끔한 파란색
    )
    embed.add_field(name="🔑 발급된 인증코드", value=f"**`{code}`**", inline=False)
    embed.add_field(name="📌 인증 게시글 링크", value=f"[👉 여기를 클릭하여 게시글로 이동]({BOARD_URL})", inline=False)
    embed.set_footer(text="댓글 작성 후 잠시만 기다리시면 자동으로 역할 부여 및 별명이 변경됩니다.")

    # ephemeral=True : 명령어를 입력한 유저에게만 보입니다! ✨
    await interaction.response.send_message(embed=embed, ephemeral=True)


def find_key_recursive(data, target_key):
    if isinstance(data, dict):
        for k, v in data.items():
            if k == target_key and v:
                return v
            if isinstance(v, (dict, list)):
                result = find_key_recursive(v, target_key)
                if result:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = find_key_recursive(item, target_key)
            if result:
                return result
    return None


async def check_comments_api_loop():
    await client.wait_until_ready()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    while not client.is_closed():
        try:
            if pending_verifications:
                print(f"🔍 [API 감시 중] 대기 인원: {len(pending_verifications)}명")

                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.get(COMMENT_API_URL) as response:
                        if response.status == 200:
                            data = await response.json()
                            content_list = data.get("contentList", [])

                            completed_users = []

                            for user_id, code in pending_verifications.items():
                                target_comment = None

                                # 1. 작성된 댓글 목록 중 인증코드가 들어있는 댓글 찾기
                                for item in content_list:
                                    if code in str(item):
                                        target_comment = item
                                        break

                                if target_comment:
                                    print(f"✅ [코드 감지 성공] 인증코드({code}) 발견!")

                                    # 2. 깊은 재귀 탐색으로 gameCharacterName 가져오기
                                    board_nickname = (
                                        find_key_recursive(target_comment, "gameCharacterName") or 
                                        find_key_recursive(target_comment, "nickname") or 
                                        find_key_recursive(target_comment, "characterName")
                                    )

                                    print(f"🏷️ 추출된 게임 캐릭터 닉네임: {board_nickname}")

                                    # 3. 디스코드 서버 및 멤버 정보 가져오기
                                    guild = client.get_guild(GUILD_ID)
                                    if not guild:
                                        print(f"❌ [오류] GUILD_ID({GUILD_ID}) 서버를 찾을 수 없습니다.")
                                        continue

                                    member = None
                                    try:
                                        member = await guild.fetch_member(int(user_id))
                                    except Exception as e:
                                        print(f"⚠️ 멤버 조회 실패: {e}")

                                    role = guild.get_role(ROLE_ID)

                                    if member and role:
                                        try:
                                            # A. 역할 부여
                                            await member.add_roles(role)
                                            print(f"🎉 [{member.display_name}] 님에게 '{role.name}' 역할 부여 성공!")

                                            # B. 게임 캐릭터 닉네임으로 서버 별명(Nick) 변경
                                            if board_nickname:
                                                try:
                                                    await member.edit(nick=str(board_nickname))
                                                    print(f"✨ [{member.display_name}] 님의 별명을 '{board_nickname}'(으)로 변경했습니다!")
                                                except discord.Forbidden:
                                                    print("❌ [권한 오류] 봇의 역할 순위가 낮거나 서버 소유자/관리자 계정입니다.")
                                                except Exception as e:
                                                    print(f"⚠️ 별명 변경 실패: {e}")

                                            # C. 알림 채널 전송
                                            channel = guild.get_channel(NOTIFICATION_CHANNEL_ID)
                                            if channel:
                                                nick_msg = f" (설정된 별명: **{board_nickname}**)" if board_nickname else ""
                                                await channel.send(
                                                    f"✅ {member.mention}님, 게시판 인증이 완료되어 **{role.name}** 역할이 부여되었습니다!{nick_msg}"
                                                )

                                        except discord.Forbidden:
                                            print("❌ [권한 오류] 봇의 역할 순위를 최상단으로 올려주세요!")
                                        except Exception as e:
                                            print(f"❌ 처리 실패: {e}")

                                    completed_users.append(user_id)

                            # 완료된 유저 목록에서 삭제
                            for user_id in completed_users:
                                del pending_verifications[user_id]
                        else:
                            print(f"⚠️ API 요청 실패 상태 코드: {response.status}")

        except Exception as e:
            print(f"⚠️ 감시 루프 오류: {e}")

        await asyncio.sleep(20)


async def main():
    while True:
        try:
            print("🚀 디스코드 서버에 연결을 시도합니다...")
            # BOT_TOKEN을 사용해 봇을 시작합니다.
            await client.start(BOT_TOKEN)
        except Exception as e:
            print(f"⚠️ 연결 중 오류 발생: {e}")
            print("🔄 5초 후 자동으로 재연결을 시도합니다...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 사용자가 직접 터미널에서 봇을 종료했습니다. (Ctrl+C)")
