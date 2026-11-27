import asyncio, time, re, unicodedata
import discord
import aiohttp

DURATIONS={'5 minutos':300,'30 minutos':1800,'1 hora':3600,'24 horas':86400,'7 dias':604800,'Permanente':0}

async def setup_punicoes(bot,guild,cfg,save):
    owner=guild.owner_id
    rb=bot.roblox_session; lock=bot.roblox_lock
    records=cfg.setdefault('punicoes637',{})
    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True),await guild.fetch_member(owner):discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)}
    staff_roles={}
    for name,limit in [('Moderador',3600),('Administrador',604800)]:
        matches=[r for r in guild.roles if r.name==name and not r.is_default() and not r.managed]
        if len(matches)==1:
            role=matches[0]; staff_roles[role.id]=(name,limit)
            overwrites[role]=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True)
        else: print('Punições: cargo ausente ou duplicado:',name,flush=True)
    ch=guild.get_channel(cfg.get('punicoes_channel',0))
    if ch is not None and not isinstance(ch,discord.TextChannel):
        raise RuntimeError('ID do painel não corresponde a um canal de texto.')
    if ch is None:
        candidates=[c for c in guild.text_channels if c.name=='painel-de-punições']
        if len(candidates)>1:
            raise RuntimeError('Painéis duplicados: mantenha apenas um canal com o nome painel-de-punições.')
        if candidates:
            ch=candidates[0]
            # Adopt only a channel containing a panel authored by this bot.
            found=False
            async for m in ch.history(limit=100):
                if m.author.id==bot.user.id and any(e.title=='⚖️ CENTRAL DE PUNIÇÕES' for e in m.embeds):
                    found=True; break
            if not found:
                raise RuntimeError('Canal existente sem painel reconhecido; confirme com a staff.')
        else:
            ch=await guild.create_text_channel('painel-de-punições',overwrites=overwrites,reason='Painel de punições')
    await ch.edit(overwrites=overwrites)
    cfg['punicoes_channel']=ch.id; save()
    def authority(i):
        if i.guild_id!=guild.id or i.channel_id!=ch.id: return None
        if i.user.id==owner: return ('Proprietário',None)
        roles=[staff_roles[r.id] for r in getattr(i.user,'roles',[]) if r.id in staff_roles]
        return max(roles,key=lambda x:x[1]) if roles else None
    async def guard(i,duration=None,owner_only=False):
        auth=authority(i)
        if auth and (not owner_only or i.user.id==owner) and (duration is None or auth[1] is None or 0<duration<=auth[1]): return True
        await i.response.send_message('Sem autorização para esta operação ou duração.',ephemeral=True); return False
    async def lookup(name):
        if not re.fullmatch(r'[A-Za-z0-9_]{3,20}',name): raise ValueError('Informe o username exato, não o nome de exibição.')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.post('https://users.roblox.com/v1/usernames/users',json={'usernames':[name],'excludeBannedUsers':False}) as r:
                r.raise_for_status(); data=(await r.json())['data']
        if len(data)!=1 or data[0]['name'].lower()!=name.lower(): raise ValueError('Username não encontrado.')
        return data[0]
    async def change(uid,block):
        async with lock:
            return await rb.change_block(uid,block)
    async def publish_record(uid, rec):
        def normalized(name):
            return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', name.casefold()).encode('ascii','ignore').decode())
        channels=[c for c in await guild.fetch_channels() if isinstance(c,discord.TextChannel) and normalized(c.name)=='registrodepunicoes']
        if len(channels)!=1:
            raise RuntimeError('Canal de registro ausente ou duplicado. Confira o nome #registro-de-punições.')
        channel=channels[0]
        permissions=channel.permissions_for(guild.me)
        if not permissions.view_channel or not permissions.send_messages:
            raise RuntimeError('DUCORTINHO precisa de Ver canal e Enviar mensagens em #'+channel.name)
        if not permissions.embed_links:
            raise RuntimeError('DUCORTINHO precisa de Inserir links em #'+channel.name)
        duration=next((label for label, seconds in DURATIONS.items() if seconds==rec['duration']),str(rec['duration'])+' segundos')
        embed=discord.Embed(title='🚨 REGISTRO DE PUNIÇÃO',colour=0xED4245)
        embed.add_field(name='👤 Jogador',value=f"[@{rec['name']}](https://www.roblox.com/users/{uid}/profile)",inline=False)
        embed.add_field(name='⏳ Duração',value=duration,inline=True)
        embed.add_field(name='📋 Motivo',value=rec['reason'][:1024],inline=False)
        embed.add_field(name='🛡️ Aplicada por',value=f"<@{rec['staff_id']}> • {rec['staff_role']}",inline=False)
        embed.add_field(name='📅 Aplicada em',value=f"<t:{rec['confirmed_at']}:F>",inline=False)
        embed.add_field(name='🔓 Término previsto',value=f"<t:{rec['expires']}:F>" if rec['expires'] else 'Permanente',inline=False)
        embed.set_footer(text='GUIDUCORTEE RP • Punição confirmada no Roblox')
        avatar_warning=''
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get('https://thumbnails.roblox.com/v1/users/avatar-headshot',params={'userIds':uid,'size':'150x150','format':'Png','isCircular':'false'}) as response:
                    response.raise_for_status()
                    data=(await response.json()).get('data',[])
            avatar=next((x.get('imageUrl') for x in data if str(x.get('targetId'))==uid and x.get('state')=='Completed'),None)
            if avatar and avatar.startswith('https://'): embed.set_thumbnail(url=avatar)
            else: avatar_warning=' Avatar indisponível no Roblox.'
        except Exception as exc:
            avatar_warning=' Avatar indisponível no Roblox.'
            print('Registro de punição: avatar',type(exc).__name__,flush=True)
        message=await channel.send(embed=embed,allowed_mentions=discord.AllowedMentions.none())
        rec['registro_message']=message.id; save()
        return avatar_warning
    async def apply(i,user,reason,duration):
        auth=authority(i)
        if not auth or (auth[1] is not None and not 0<duration<=auth[1]): raise ValueError('Sem autorização.')
        uid=str(user['id']); existing=records.get(uid)
        if existing and existing['status'] in ('active','pending'): raise ValueError('Já existe punição ativa ou pendente.')
        rec={'name':user['name'],'reason':reason,'created':int(time.time()),'expires':0,'status':'pending','duration':duration,'staff_id':i.user.id,'staff_role':auth[0]}; records[uid]=rec; save()
        try:
            changed=await change(uid,True)
            if not changed: raise RuntimeError('Usuário já bloqueado anteriormente; desbloqueio automático não autorizado.')
        except Exception:
            rec['status']='review'; save(); raise
        confirmed_at=int(time.time())
        rec.update(status='active',confirmed_at=confirmed_at,expires=confirmed_at+duration if duration else 0); save()
        notice=''
        try:
            notice=' Registro publicado em #registro-de-punições.'+await publish_record(uid,rec)
        except Exception as exc:
            print('Falha ao publicar registro:',type(exc).__name__,str(exc)[:300],flush=True)
            notice=' Atenção: bloqueio ativo, mas falhou a publicação do registro: '+str(exc)[:200]
        await i.followup.send('Bloqueio confirmado no Roblox. A saída do jogo não foi verificada.'+notice,ephemeral=True)
    async def revoke(uid):
        rec=records[uid]
        if rec['status']!='active': raise ValueError('Punição não ativa.')
        await change(uid,False); rec['status']='revoked'; save()
    class Confirm(discord.ui.View):
        def __init__(self,user,reason,duration,actor): super().__init__(timeout=120); self.user=user; self.reason=reason; self.duration=duration; self.actor=actor
        @discord.ui.button(label='Confirmar bloqueio',style=discord.ButtonStyle.danger)
        async def confirm(self,i,b):
            if i.user.id!=self.actor:
                await i.response.send_message("Confirmação exclusiva do solicitante.",ephemeral=True); return
            if not await guard(i,self.duration): return
            await i.response.defer(ephemeral=True,thinking=True); self.stop()
            try: await apply(i,self.user,self.reason,self.duration)
            except Exception as e: await i.followup.send('Não confirmado: '+str(e)[:300],ephemeral=True)
    class Form(discord.ui.Modal,title='Aplicar punição'):
        username=discord.ui.TextInput(label='Username exato',max_length=20)
        reason=discord.ui.TextInput(label='Motivo',max_length=200)
        duration=discord.ui.TextInput(label='Duração predefinida',placeholder='5 minutos, 30 minutos, 1 hora, 24 horas, 7 dias, Permanente',max_length=20)
        async def on_submit(self,i):
            if not await guard(i): return
            await i.response.defer(ephemeral=True,thinking=True)
            try:
                d=DURATIONS.get(self.duration.value.strip());
                if d is None: raise ValueError('Escolha: '+', '.join(DURATIONS))
                auth=authority(i)
                if not auth or (auth[1] is not None and not 0<d<=auth[1]): raise ValueError('Duração não autorizada para seu cargo.')
                user=await lookup(self.username.value.strip())
                await i.followup.send(f"Confirme @{user['name']} — ID {user['id']}\nhttps://www.roblox.com/users/{user['id']}/profile\nDuração: {self.duration.value}\nMotivo: {self.reason.value}",view=Confirm(user,self.reason.value,d,i.user.id),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
            except Exception as e: await i.followup.send(str(e)[:300],ephemeral=True)
    class Revoke(discord.ui.Modal,title='Revogar punição'):
        username=discord.ui.TextInput(label='Username exato',max_length=20)
        async def on_submit(self,i):
            if not await guard(i,owner_only=True): return
            await i.response.defer(ephemeral=True,thinking=True)
            try:
                u=await lookup(self.username.value.strip()); await revoke(str(u['id'])); await i.followup.send('Desbloqueio confirmado.',ephemeral=True)
            except Exception as e: await i.followup.send('Não confirmado: '+str(e)[:300],ephemeral=True)
    class Panel(discord.ui.View):
        def __init__(self): super().__init__(timeout=None)
        @discord.ui.button(label='Aplicar punição',style=discord.ButtonStyle.danger,custom_id='pun637:apply')
        async def start(self,i,b):
            if await guard(i): await i.response.send_modal(Form())
        @discord.ui.button(label='Revogar punição',style=discord.ButtonStyle.success,custom_id='pun637:revoke')
        async def end(self,i,b):
            if await guard(i,owner_only=True): await i.response.send_modal(Revoke())
        @discord.ui.button(label='Consultar punições',custom_id='pun637:list')
        async def history(self,i,b):
            if not await guard(i): return
            lines=[f"{r['name']} | {r['status']} | {r['reason']} | "+(f"<t:{r['expires']}:R>" if r['expires'] else 'sem prazo') for r in records.values()]
            await i.response.send_message(('\n'.join(lines)[-1800:] or 'Nenhuma punição.'),ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
    view=Panel(); bot.add_view(view)
    embed=discord.Embed(title='⚖️ CENTRAL DE PUNIÇÕES',description='Moderador: até 1 hora. Administrador: até 7 dias. Proprietário: todas as durações e revogação. Informe o username exato e confirme o perfil. Durações: '+', '.join(DURATIONS),colour=0xD50000)
    msg=None
    if cfg.get('punicoes_message'):
        try: msg=await ch.fetch_message(cfg['punicoes_message'])
        except discord.NotFound: pass
    if msg and (msg.author.id!=bot.user.id or not any(e.title==embed.title for e in msg.embeds)):
        msg=None
    if not msg:
        async for candidate in ch.history(limit=100):
            if candidate.author.id==bot.user.id and any(e.title==embed.title for e in candidate.embeds):
                msg=candidate; break
    if msg: await msg.edit(embed=embed,view=view)
    else: msg=await ch.send(embed=embed,view=view)
    cfg['punicoes_message']=msg.id; save()
    async def expire():
        while not bot.is_closed():
            for uid,r in list(records.items()):
                if r['status']=='active' and r['expires'] and r['expires']<=time.time():
                    try: await revoke(uid)
                    except Exception as e: print('Desbloqueio pendente:',uid,type(e).__name__)
            await asyncio.sleep(60)
    bot.punicoes_task=asyncio.create_task(expire())
    print('PRONTO! Painel experimental de punições.')
