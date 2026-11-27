import asyncio
import time
import discord
from roblox import Roblox

RP_SECONDS = 90 * 60
WARNING_SECONDS = 5 * 60
RESET_SECONDS = 5 * 60

async def setup_city(bot,guild,cfg,save):
    channels=[c for c in guild.text_channels if c.name=='status-da-cidade']
    if len(channels)!=1: raise RuntimeError('Canal status-da-cidade ausente ou duplicado.')
    ch=channels[0]; state=cfg.setdefault('city',{}); rb=Roblox(); lock=asyncio.Lock(); bot.roblox_session=rb; bot.roblox_lock=lock
    state.update(start=0,phase='unknown'); save()
    task=None; panel=None; marker='GUIDUCORTEE RP • Controle da cidade v6'
    def embed(phase,link=None,deadline=None):
        titles={'open':'🟢 CIDADE ABERTA','closed':'🔴 CIDADE FECHADA','unknown':'⚠️ STATUS NÃO CONFIRMADO'}
        e=discord.Embed(title=titles[phase],colour={'open':0x23A559,'closed':0xED4245,'unknown':0xF0B232}[phase])
        if link: e.description='[Entrar no servidor privado]('+link+')'
        if deadline: e.add_field(name='Próximo reset' if phase=='open' else 'Reabertura prevista',value=f'<t:{deadline}:R>')
        if phase=='unknown': e.description='Staff: confirme o estado no Roblox antes de iniciar.'
        e.set_footer(text=marker); return e
    async def publish(phase,link=None,deadline=None):
        state.update(phase=phase,start=int(time.time()) if phase=='open' else 0); save()
        e=embed(phase,link,deadline)
        await panel.edit(embed=e,view=view)
        await ch.send(embed=e,allowed_mentions=discord.AllowedMentions.none())
    async def cycle():
        try:
            while True:
                async with lock:
                    # Always invalidate any old invitation before opening a new session.
                    await rb.close(); link=await rb.open()
                    await publish('open',link,int(time.time())+RP_SECONDS)
                await asyncio.sleep(RP_SECONDS - WARNING_SECONDS)
                await ch.send('⚠️ Faltam 5 minutos para o reset da cidade.')
                await asyncio.sleep(WARNING_SECONDS)
                async with lock:
                    await rb.close(); await publish('closed',deadline=int(time.time())+RESET_SECONDS)
                await asyncio.sleep(RESET_SECONDS)
        except asyncio.CancelledError: raise
        except Exception as exc:
            print('Falha Roblox:',type(exc).__name__,'— etapa:',rb.stage)
            try: await publish('unknown')
            except Exception: pass
    class View(discord.ui.View):
        def __init__(self): super().__init__(timeout=None)
        async def allowed(self,i):
            if i.guild_id!=guild.id or i.channel_id!=ch.id or not i.user.guild_permissions.manage_guild:
                await i.response.send_message('Somente staff autorizada.',ephemeral=True); return False
            await i.response.defer(ephemeral=True,thinking=True); return True
        @discord.ui.button(label='Iniciar ciclo automático',style=discord.ButtonStyle.success,custom_id='guiducortee:city:v6:start')
        async def start(self,i,b):
            nonlocal task
            if not await self.allowed(i): return
            async with lock:
                if task and not task.done(): msg='Ciclo já ativo.'
                else: task=asyncio.create_task(cycle()); msg='Ciclo iniciado. Aguarde confirmação do Roblox no painel.'
            await i.followup.send(msg,ephemeral=True)
        @discord.ui.button(label='Encerrar ciclo e fechar',style=discord.ButtonStyle.danger,custom_id='guiducortee:city:v6:stop')
        async def stop(self,i,b):
            nonlocal task
            if not await self.allowed(i): return
            async with lock:
                if task and not task.done():
                    task.cancel()
                    try: await task
                    except asyncio.CancelledError: pass
                try: await rb.close(); await publish('closed'); msg='Servidor fechado e ciclo encerrado.'
                except Exception as exc:
                    print('Falha Roblox:',type(exc).__name__,'— etapa:',rb.stage)
                    await publish('unknown'); msg='Ciclo encerrado, mas fechamento não confirmado. Confira manualmente.'
            await i.followup.send(msg,ephemeral=True)
    view=View()
    if state.get('message'):
        try: panel=await ch.fetch_message(state['message'])
        except discord.NotFound: pass
    if panel is None: panel=await ch.send(embed=embed('unknown'),view=view)
    else: await panel.edit(embed=embed('unknown'),view=view)
    state['message']=panel.id; save(); bot.add_view(view,message_id=panel.id)
    print('PRONTO! Controle Roblox em #status-da-cidade. RP: 90 minutos; intervalo: 5 minutos. Inicie pela staff.')
