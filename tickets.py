import asyncio
import discord

STAFF={'Fundador','Diretor','Administrador','Moderador','Fiscal de RP','Suporte'}
KINDS={'suporte':'Suporte geral','denuncia':'Denúncia de jogador','punicao':'Revisão de punição','bug':'Reportar bug','outros':'Outros assuntos'}
MARK='GUIDUCORTEE RP • Tickets v636'

async def setup_tickets(bot,guild,cfg,save):
    cats=[c for c in guild.categories if 'ATENDIMENTO' in c.name.upper()]
    if len(cats)!=1: raise RuntimeError('É necessária uma categoria ATENDIMENTO única.')
    cat=cats[0]
    panels=[c for c in cat.text_channels if c.name=='abrir-ticket']
    if len(panels)!=1: raise RuntimeError('É necessário um canal #abrir-ticket único em ATENDIMENTO.')
    panel=panels[0]; lock=asyncio.Lock()
    def staff_roles():
        return [r for r in guild.roles if r.name in STAFF and sum(x.name==r.name for x in guild.roles)==1]
    def authorized(member):
        return isinstance(member,discord.Member) and (member.guild_permissions.administrator or any(r in staff_roles() for r in member.roles))
    def owner(ch):
        topic=ch.topic or ''
        if ch.category_id!=cat.id or not topic.startswith('guiducortee-ticket:'): return None
        value=topic.split(':')[1]
        return int(value) if value.isdecimal() else None
    class Close(discord.ui.View):
        def __init__(self): super().__init__(timeout=None)
        @discord.ui.button(label='Fechar ticket',emoji='🔒',style=discord.ButtonStyle.danger,custom_id='guiducortee:ticket:close:636')
        async def close(self,i,b):
            if i.guild_id!=guild.id or not isinstance(i.channel,discord.TextChannel) or not owner(i.channel) or not authorized(i.user):
                await i.response.send_message('Somente a staff pode fechar tickets.',ephemeral=True); return
            class Confirm(discord.ui.View):
                def __init__(self): super().__init__(timeout=60)
                @discord.ui.button(label='Confirmar exclusão',style=discord.ButtonStyle.danger)
                async def confirm(self,j,b):
                    if j.user.id!=i.user.id or not authorized(j.user) or not owner(j.channel):
                        await j.response.send_message('Sem autorização.',ephemeral=True); return
                    await j.response.defer(ephemeral=True)
                    try: await j.channel.delete(reason=f'Ticket fechado por {j.user.id}')
                    except discord.HTTPException: await j.followup.send('Não consegui excluir o ticket.',ephemeral=True)
            await i.response.send_message('Excluir este ticket e seu histórico? Salve as informações necessárias antes.',view=Confirm(),ephemeral=True)
    class Open(discord.ui.View):
        def __init__(self): super().__init__(timeout=None)
        @discord.ui.select(placeholder='Selecione o motivo do atendimento',custom_id='guiducortee:ticket:open:636',options=[discord.SelectOption(label=v,value=k) for k,v in KINDS.items()])
        async def create(self,i,select):
            if i.guild_id!=guild.id or i.channel_id!=panel.id or not isinstance(i.user,discord.Member):
                await i.response.send_message('Painel indisponível.',ephemeral=True); return
            await i.response.defer(ephemeral=True,thinking=True)
            try:
                async with lock:
                    existing=next((c for c in cat.text_channels if owner(c)==i.user.id),None)
                    if existing:
                        await i.followup.send('Você já possui um ticket: '+existing.mention,ephemeral=True); return
                    roles=staff_roles()
                    if not roles: raise RuntimeError('Nenhum cargo de staff encontrado.')
                    allow=discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,attach_files=True,embed_links=True)
                    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=False),i.user:allow,guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,read_message_history=True,manage_channels=True,embed_links=True)}
                    overwrites.update({r:allow for r in roles})
                    kind=select.values[0]
                    ch=await guild.create_text_channel(f'ticket-{i.user.id}',category=cat,topic=f'guiducortee-ticket:{i.user.id}:{kind}',overwrites=overwrites,reason='Atendimento solicitado')
                    embed=discord.Embed(title='🎫 '+KINDS[kind],description='Descreva sua solicitação e aguarde a staff. Não envie senhas, tokens ou documentos pessoais.',colour=0xD50000)
                    await ch.send(i.user.mention,embed=embed,view=Close(),allowed_mentions=discord.AllowedMentions(users=True,roles=False,everyone=False))
                    await i.followup.send('Ticket criado: '+ch.mention,ephemeral=True)
            except Exception as e:
                print('Erro ticket:',type(e).__name__,str(e)); await i.followup.send('Não foi possível concluir. Avise a staff.',ephemeral=True)
    bot.add_view(Close()); view=Open(); bot.add_view(view)
    embed=discord.Embed(title='🎫 CENTRAL DE ATENDIMENTO',description='Selecione o motivo abaixo para abrir um ticket privado com a staff. Apenas um ticket por pessoa.',colour=0xD50000); embed.set_footer(text=MARK)
    msg=None
    if cfg.get('ticket_message'):
        try: msg=await panel.fetch_message(cfg['ticket_message'])
        except discord.NotFound: pass
    if not msg:
        async for m in panel.history(limit=100):
            if m.author.id==bot.user.id and any(e.footer.text==MARK for e in m.embeds): msg=m; break
    if msg: await msg.edit(embed=embed,view=view)
    else: msg=await panel.send(embed=embed,view=view)
    cfg['ticket_message']=msg.id; save(); print('PRONTO! Tickets em #abrir-ticket')
