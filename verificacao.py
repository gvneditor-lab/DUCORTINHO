import discord
import asyncio

STAFF = {'Fundador','Diretor','Administrador','Moderador','Fiscal de RP','Suporte'}
SAFE = {'read_messages','view_channel','read_message_history','send_messages','connect','speak','add_reactions','attach_files','embed_links','use_application_commands','send_messages_in_threads','create_public_threads','use_external_emojis','use_external_stickers','stream','use_voice_activation','use_embedded_activities','use_soundboard','use_external_sounds','send_voice_messages','send_polls','use_external_apps','change_nickname','request_to_speak','create_private_threads','use_external_apps','send_polls','use_voice_activation'}

def unique(items, name):
    matches = [x for x in items if x.name == name]
    if len(matches) != 1:
        raise RuntimeError('Ausente ou duplicado: '+name)
    return matches[0]

def check_role(guild, role):
    if role.managed or role >= guild.me.top_role or {k for k,v in role.permissions if v} - SAFE:
        raise RuntimeError('Cargo de verificação inseguro ou acima do bot: '+role.name)
    for channel in guild.channels:
        grants = {k for k,v in channel.overwrites_for(role) if v is True}
        if grants - SAFE:
            raise RuntimeError('Permissão privilegiada no cargo '+role.name+' em '+channel.name+': '+', '.join(sorted(grants-SAFE)))
        category = channel.name if isinstance(channel, discord.CategoryChannel) else (channel.category.name if channel.category else '')
        if grants and any(x in category.upper() for x in ('ADMINISTRA','POLÍCIA','SAMU','SUBMUNDO')):
            raise RuntimeError('Cargo de verificação possui acesso restrito: '+channel.name)

async def setup_verification(bot, guild, cfg, save, locks):
    role = unique(guild.roles, 'Cidadão verificado')
    pending = [r for r in guild.roles if r.name == 'Não verificado']
    if len(pending)>1: raise RuntimeError('Cargo Não verificado duplicado.')
    channels = [c for c in guild.text_channels if c.name in ('verificação','verificacao')]
    if len(channels)>1: raise RuntimeError('Canal de verificação duplicado.')
    if channels: ch=channels[0]
    else:
        cat=next((c for c in guild.categories if 'RECEPÇÃO' in c.name.upper()),None)
        ch=await guild.create_text_channel('verificação',category=cat)
    chat_matches = [c for c in guild.text_channels if c.name == 'chat-geral']
    chat = chat_matches[0] if len(chat_matches)==1 else None
    async def update(channel,target,**kwargs):
        ow=channel.overwrites_for(target)
        ow.update(**kwargs)
        await channel.set_permissions(target,overwrite=ow,reason='Verificação Guiducortee V6.3.3')
    async def prepare_access():
        check_role(guild, role)
        if pending and (pending[0].managed or pending[0] >= guild.me.top_role):
            raise RuntimeError('Cargo Não verificado acima do bot ou gerenciado.')
        if chat is None: raise RuntimeError('Canal chat-geral ausente ou duplicado.')
        await update(chat,guild.default_role,send_messages=False,send_messages_in_threads=False,create_public_threads=False,create_private_threads=False)
        await update(chat,role,view_channel=True,read_message_history=True,send_messages=True)
        if pending: await update(chat,pending[0],send_messages=False,send_messages_in_threads=False)
        for target, ow in chat.overwrites.items():
            if target in (guild.default_role,role,guild.me) or target in pending: continue
            if isinstance(target,discord.Role) and (target.name in STAFF or target.managed or target.permissions.administrator): continue
            if ow.send_messages is True or ow.send_messages_in_threads is True:
                print('ATENÇÃO: permissão extra de escrita em chat-geral:',target.name)
    access_error = None
    try:
        await prepare_access()
    except Exception as e:
        access_error = str(e)
        print('Verificação: painel será publicado, mas atribuição bloqueada:', access_error)
    try:
        await update(ch,guild.default_role,view_channel=True,read_message_history=True,send_messages=False)
        await update(ch,guild.me,view_channel=True,read_message_history=True,send_messages=True,embed_links=True)
        if pending: await update(ch,pending[0],view_channel=True,read_message_history=True,send_messages=False)
    except discord.HTTPException as e:
        print('Verificação: não foi possível ajustar acesso ao painel:', str(e))
    class Verify(discord.ui.View):
        def __init__(self): super().__init__(timeout=None)
        @discord.ui.button(label='Realizar verificação',emoji='✅',style=discord.ButtonStyle.success,custom_id='guiducortee:verify:v5')
        async def verify(self, interaction, button):
            if interaction.guild_id!=guild.id or interaction.channel_id!=ch.id or not isinstance(interaction.user,discord.Member):
                await interaction.response.send_message('Painel indisponível.',ephemeral=True); return
            await interaction.response.defer(ephemeral=True,thinking=True)
            try:
                async with locks.setdefault(interaction.user.id,asyncio.Lock()):
                    member=await guild.fetch_member(interaction.user.id)
                    current=unique(guild.roles,'Cidadão verificado')
                    if current.id!=role.id: raise RuntimeError('Cargo alterado. Reinicie o bot.')
                    if access_error: raise RuntimeError(access_error)
                    check_role(guild,current)
                    if member.pending: raise RuntimeError('Aceite primeiro as regras de entrada do Discord.')
                    if current not in member.roles: await member.add_roles(current,reason='Aceite das regras pelo painel')
                    for r in member.roles:
                        if r.name=='Não verificado':
                            if r.managed or r >= guild.me.top_role: raise RuntimeError('Não verificado acima do bot ou gerenciado.')
                            await member.remove_roles(r,reason='Verificação concluída')
                    choices = [c for c in guild.text_channels if c.name == 'escolher-cargos' and c.category and 'RECEPÇÃO' in c.category.name.upper()]
                    destination = choices[0].mention if len(choices) == 1 else '#escolher-cargos'
                    await interaction.followup.send('✅ Você está verificado! Agora você já pode conversar na cidade. Acesse '+destination+' para selecionar seus cargos e sua equipe.',ephemeral=True)
            except Exception as e:
                print('Erro verificação:',type(e).__name__,str(e))
                await interaction.followup.send('Não foi possível concluir a verificação. Avise a staff e tente novamente.',ephemeral=True)
    view=Verify()
    marker='GUIDUCORTEE RP • Verificação v5'
    embed=discord.Embed(title='🛡️ VERIFICAÇÃO DE CIDADÃO',description='Seja bem-vindo ao Guiducortee RP!\n\nLeia as regras e clique abaixo para liberar o chat e a seleção de equipes. Ao clicar, você concorda com o regulamento. Não envie documentos, senhas ou tokens.',colour=0xD50000)
    embed.set_footer(text=marker)
    msg=None
    if cfg.get('verification_message'):
        try: msg=await ch.fetch_message(cfg['verification_message'])
        except discord.NotFound: pass
    if not msg:
        async for candidate in ch.history(limit=100):
            if candidate.author.id==bot.user.id and any(e.footer.text==marker for e in candidate.embeds): msg=candidate; break
    if msg: await msg.edit(embed=embed,view=view)
    else: msg=await ch.send(embed=embed,view=view)
    cfg['verification_message']=msg.id; save()
    bot.add_view(view,message_id=msg.id)
    print('V6.3.3 PRONTO! Painel de verificação em #'+ch.name + (' (atribuição bloqueada: '+access_error+')' if access_error else ''))
