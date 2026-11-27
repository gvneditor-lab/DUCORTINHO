import asyncio, getpass, re, json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
import discord
from discord.ext import commands

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config.json'
GROUPS = {
 'idade': ('🎂 Faixa etária (opcional e pública)', [('Menor de 18 anos','Idade • Menor de 18'),('18 anos ou mais','Idade • 18+'),('Prefiro não informar',None)],0x95A5A6),
 'genero': ('👤 Gênero (opcional e público)', [('Masculino','Gênero • Masculino'),('Feminino','Gênero • Feminino'),('Outro','Gênero • Outro'),('Prefiro não informar',None)],0x95A5A6),
 'plataforma': ('🎮 Plataforma', [('PC','Plataforma • PC'),('Mobile','Plataforma • Mobile'),('Console','Plataforma • Console'),('Remover seleção',None)],0x3498DB),
 'avisos': ('🔔 Notificações', [('Abertura da cidade','Avisos • Cidade'),('Eventos','Avisos • Eventos'),('Sorteios','Avisos • Sorteios'),('Todas as notificações','ALL'),('Sem notificações',None)],0xE67E22),
}

def save():
 tmp=CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(CONFIG)

def token_input():
 import os
 token=os.environ.get('DISCORD_TOKEN','').strip()
 if not token: raise RuntimeError('Configure DISCORD_TOKEN no ambiente da hospedagem.')
 return token

cfg=json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.exists() else {}
if 'guild' not in cfg:
 raise RuntimeError('Informe guild em config.json.')
intents=discord.Intents.default()
bot=commands.Bot(command_prefix='!',intents=intents)
locks={}

def names(group):
 return [r for _,r in GROUPS[group][1] if r and r!='ALL']

class Menu(discord.ui.Select):
 def __init__(self,group):
  self.group=group
  title, opts, _=GROUPS[group]
  super().__init__(custom_id='guiducortee:auto:v1:'+group,placeholder=title,max_values=1,min_values=1,options=[discord.SelectOption(label=label,value=str(i)) for i,(label,_) in enumerate(opts)])
 async def callback(self,interaction):
  await interaction.response.defer(ephemeral=True,thinking=True)
  if interaction.guild_id!=cfg['guild'] or not isinstance(interaction.user,discord.Member):
   await interaction.followup.send('Painel indisponível neste servidor.',ephemeral=True); return
  try:
   async with locks.setdefault(interaction.user.id,asyncio.Lock()):
    guild=interaction.guild; member=await guild.fetch_member(interaction.user.id)
    roles={n:guild.get_role(cfg['roles'][n]) for n in names(self.group)}
    if any(r is None or r.managed or r.permissions.value!=0 or r>=guild.me.top_role for r in roles.values()):
     raise RuntimeError('Cargo ausente, privilegiado ou acima do bot. Avise a staff.')
    selected=GROUPS[self.group][1][int(self.values[0])][1]
    desired=set(roles.values()) if selected=='ALL' else ({roles[selected]} if selected else set())
    current=set(member.roles)&set(roles.values())
    if current-desired: await member.remove_roles(*(current-desired),reason='Autocargos')
    if desired-current: await member.add_roles(*(desired-current),reason='Autocargos')
    await interaction.followup.send('✅ Preferências atualizadas: '+(', '.join(r.name for r in desired) if desired else 'nenhum cargo nesta categoria'),ephemeral=True)
  except Exception as e:
   print('Erro de interação:',type(e).__name__,str(e)); await interaction.followup.send('Não foi possível atualizar todos os cargos. Confira as permissões e tente novamente.',ephemeral=True)

class Panel(discord.ui.View):
 def __init__(self):
  super().__init__(timeout=None)
  for group in GROUPS: self.add_item(Menu(group))
  self.add_item(TeamMenu())

PROFESSIONS = {
 'civil': ('Civil', ['Civil','Trabalhador','Empresário','Vendedor','Entregador','Mecânico','Motociclista']),
 'crime': ('Criminoso', ['Criminoso','Traficante RP','Ladrão de motos RP','Receptador RP','Assaltante RP'])}
PROTECTED = {'Policial','Paramédico','Coronel','Capitão','Tenente','Sargento','Cabo','Soldado','Recruta PM','ROCAM','Diretor Médico','Coordenador','Médico','Socorrista','Condutor','Líder de organização'}
PROF_NAMES = {n for _, ns in PROFESSIONS.values() for n in ns}

def profession_roles(guild, required=(), held=()):
 from verificacao import SAFE
 roles = {}
 for name in PROF_NAMES:
  matches = [r for r in guild.roles if r.name == name]
  if name not in required and not any(r in held for r in matches): continue
  if len(matches) != 1:
   if name in required or any(r in held for r in matches): raise RuntimeError('Cargo necessário ausente ou duplicado: '+name+'. Avise a staff.')
   continue
  r = matches[0]
  if r.managed or ({k for k,v in r.permissions if v} - SAFE) or r >= guild.me.top_role: raise RuntimeError('Cargo inseguro ou acima do bot: '+name)
  # Only allow existing channel grants in the intended department; reject management grants anywhere.
  allowed = 'TRABALHADORES' if name in PROFESSIONS['civil'][1] else 'SUBMUNDO RP'
  for ch in guild.channels:
   ow = ch.overwrites_for(r)
   grants = {k for k,v in ow if v is True}
   if grants - SAFE: raise RuntimeError('Permissão extra no cargo '+name+' em '+ch.name+': '+', '.join(sorted(grants-SAFE)))
   if grants and allowed not in (ch.name.upper() if isinstance(ch,discord.CategoryChannel) else (ch.category.name.upper() if ch.category else '')): raise RuntimeError('Acesso inesperado no cargo '+name)
  roles[name]=r
 return roles

class TeamMenu(discord.ui.Select):
 def __init__(self):
  super().__init__(custom_id='guiducortee:team:v4',placeholder='🏙️ Escolha sua equipe',options=[discord.SelectOption(label=n,value=v,emoji=e) for n,v,e in [('Trabalhador','Trabalhador','💼'),('Civil','Civil','🟢'),('Criminoso','Criminoso','🔴'),('Polícia','pm','🚔'),('SAMU','samu','🚑')]])
 async def callback(self,interaction):
  if interaction.guild_id!=cfg['guild'] or not isinstance(interaction.user,discord.Member):
   await interaction.response.send_message('Painel indisponível.',ephemeral=True); return
  v=self.values[0]
  if v in ('pm','samu'):
   await interaction.response.send_message('Solicite aprovação da staff para '+('Polícia' if v=='pm' else 'SAMU')+'. Procure o canal de atendimento ou recrutamento.',ephemeral=True); return
  await change_profession(interaction,'crime' if v=='Criminoso' else 'civil',v)

class ProfessionMenu(discord.ui.Select):
 def __init__(self, group):
  self.group=group
  team, ns=PROFESSIONS[group]
  super().__init__(custom_id='guiducortee:profession:v2:'+group,placeholder='🟢 Profissões civis' if group=='civil' else '🔴 Profissões criminosas (RP)',options=[discord.SelectOption(label=n,value=n) for n in ns])
 async def callback(self, interaction):
  await change_profession(interaction,self.group,self.values[0])

async def change_profession(interaction,group=None,selection=None):
 await interaction.response.defer(ephemeral=True,thinking=True)
 if interaction.guild_id!=cfg['guild'] or not isinstance(interaction.user,discord.Member):
  await interaction.followup.send('Painel indisponível.',ephemeral=True); return
 try:
  async with locks.setdefault(interaction.user.id,asyncio.Lock()):
   guild=interaction.guild; member=await guild.fetch_member(interaction.user.id)
   if not any(r.name=='Cidadão verificado' for r in member.roles): raise RuntimeError('Solicite a verificação à staff primeiro.')
   if any(r.name in PROTECTED for r in member.roles): raise RuntimeError('Você possui função de recrutamento ou liderança. Procure a staff para trocar.')
   required={PROFESSIONS[group][0],selection} if group else set()
   if group=='civil' and selection!='Civil': required.add('Trabalhador')
   roles=profession_roles(guild,required,member.roles)
   desired={roles[n] for n in required}
   current=set(member.roles)&set(roles.values())
   if current-desired: await member.remove_roles(*(current-desired),reason='Troca de profissão RP')
   if desired-current: await member.add_roles(*(desired-current),reason='Escolha de profissão RP')
   await interaction.followup.send('✅ Profissão: '+(selection or 'nenhuma')+'. Não troque durante uma ação de RP.',ephemeral=True)
 except Exception as e:
  print('Erro profissão:',type(e).__name__,str(e)); await interaction.followup.send('Não foi possível concluir: '+str(e)[:300],ephemeral=True)

class ProfessionPanel(discord.ui.View):
 def __init__(self):
  super().__init__(timeout=None)
  for group in PROFESSIONS: self.add_item(ProfessionMenu(group))
 @discord.ui.button(label='Abandonar profissão',style=discord.ButtonStyle.danger,custom_id='guiducortee:profession:v2:leave')
 async def leave(self,interaction,button): await change_profession(interaction)
 @discord.ui.button(label='Polícia / SAMU: recrutamento',style=discord.ButtonStyle.secondary,custom_id='guiducortee:profession:v2:recruit')
 async def recruit(self,interaction,button):
  ch=discord.utils.get(interaction.guild.text_channels,name='recrutamento') if interaction.guild else None
  await interaction.response.send_message('Procure a staff para aprovação. '+(ch.mention if ch else 'Use o canal de atendimento.'),ephemeral=True)

async def setup_professions(guild):
 profession_roles(guild)
 channels=[c for c in guild.text_channels if c.name=='cargos-e-profissões']
 if not channels:
  print('Canal cargos-e-profissões ausente; equipe disponível em escolher-cargos.'); return
 if len(channels)!=1: raise RuntimeError('Canal cargos-e-profissões duplicado.')
 ch=channels[0]; view=ProfessionPanel(); bot.add_view(view)
 embed=discord.Embed(title='💼 ESCOLHA SEU CAMINHO',description='Escolha uma profissão civil ou criminosa fictícia. A escolha substitui a anterior e concede o time correspondente. Apenas cidadãos verificados podem escolher. Polícia e SAMU exigem aprovação da staff. Não troque durante ações de RP. Não há economia própria.',colour=0xD50000)
 marker='GUIDUCORTEE RP • Central de profissões v2'; embed.set_footer(text=marker)
 msg=None
 if cfg.get('profession_message'):
  try: msg=await ch.fetch_message(cfg['profession_message'])
  except discord.NotFound: pass
 if not msg:
  async for candidate in ch.history(limit=100):
   if candidate.author.id==bot.user.id and any(e.footer.text==marker for e in candidate.embeds): msg=candidate; break
 if msg: await msg.edit(embed=embed,view=view)
 else: msg=await ch.send(embed=embed,view=view)
 cfg['profession_message']=msg.id; save()
 print('PRONTO! Profissões em #'+ch.name)

@bot.event
async def on_ready():
 if getattr(bot,'initialized',False): return
 bot.initialized=True
 try:
  guild=bot.get_guild(cfg['guild'])
  if guild is None: raise RuntimeError('Bot não está no servidor informado.')
  me=guild.me
  if not (me.guild_permissions.manage_roles and me.guild_permissions.manage_channels): raise RuntimeError('Bot precisa de Gerenciar Cargos e Gerenciar Canais.')
  print('Servidor:',guild.name)
  cfg.setdefault('roles',{})
  for group,(_,_,color) in GROUPS.items():
   for name in names(group):
    role=guild.get_role(cfg['roles'].get(name,0))
    if role is None:
     # Do not adopt existing roles: they may have channel-specific privileges.
     role=await guild.create_role(name=name,colour=discord.Colour(color),permissions=discord.Permissions.none(),hoist=False,mentionable=False,reason='Guiducortee Autocargos')
     cfg['roles'][name]=role.id; save()
    if role.managed or role.permissions.value or role>=me.top_role: raise RuntimeError('Cargo inseguro ou acima do bot: '+name)
    print('OK:',name)
  candidates=[c for c in guild.text_channels if c.name=='escolher-cargos' and c.category and 'RECEPÇÃO' in c.category.name.upper()]
  if len(candidates)!=1: raise RuntimeError('Mantenha exatamente um #escolher-cargos na RECEPÇÃO.')
  channel=candidates[0]
  if cfg.get('channel')!=channel.id:
   cfg['channel']=channel.id; cfg.pop('message',None); save()
  if not any(r.name=='Trabalhador' for r in guild.roles):
   await guild.create_role(name='Trabalhador',colour=discord.Colour(0x2ECC71),permissions=discord.Permissions.none(),reason='Equipe trabalhador')
  embed=discord.Embed(title='🎭 PERSONALIZE SEU PERFIL',description='Escolha seus cargos nos menus abaixo. Você pode alterar ou remover suas escolhas a qualquer momento.\n\nIdade e gênero são opcionais e públicos. Não informe sua idade exata. Escolha sua equipe no menu abaixo. Polícia e SAMU exigem aprovação da staff.\n\nPara avisos, escolha uma opção, todas ou nenhuma.',colour=0xD50000)
  embed.set_footer(text='GUIDUCORTEE RP • Sistema de autocargos')
  view=Panel(); bot.add_view(view)
  message=None
  if cfg.get('message'):
   try: message=await channel.fetch_message(cfg['message'])
   except discord.NotFound: pass
  if not message:
   async for candidate in channel.history(limit=100):
    if candidate.author.id==bot.user.id and any(e.footer.text==embed.footer.text for e in candidate.embeds): message=candidate; break
  if message: await message.edit(embed=embed,view=view); cfg['message']=message.id; save()
  else:
   message=await channel.send(embed=embed,view=view); cfg['message']=message.id; save()
  print('PRONTO! Painel em #'+channel.name+'. Mantenha esta janela aberta.')
  try:
   from cidade import setup_city
   await setup_city(bot,guild,cfg,save)
  except Exception as e: print('Controle da cidade não instalado:',str(e))
  try:
   from verificacao import setup_verification
   await setup_verification(bot,guild,cfg,save,locks)
  except Exception as e: print('Verificação não instalada:',str(e))
  try:
   from tickets import setup_tickets
   await setup_tickets(bot,guild,cfg,save)
  except Exception as e: print('Tickets não instalados:',str(e))
  try:
   from punicoes import setup_punicoes
   await setup_punicoes(bot,guild,cfg,save)
  except Exception as e: print("Punições não instaladas:",str(e))
  try: await setup_professions(guild)
  except Exception as e: print('Profissões não instaladas:',str(e),'— autocargos continuam ativos.')
 except Exception as e:
  print('ERRO:',type(e).__name__,str(e)); await bot.close()

if __name__=='__main__':
 try: bot.run(token_input(),log_handler=None)
 except Exception as e: print('ERRO:',type(e).__name__,str(e))
