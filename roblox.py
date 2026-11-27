
"""DUCORTINHO Cloud V1.6 - Experimental HTTP backend."""
import os, asyncio, aiohttp
from urllib.parse import urlencode

class Roblox:
    stage='inicialização'

    def __init__(self):
        self.id=int(os.getenv('ROBLOX_SERVER_ID','5048828340'))
        self.csrf=''

    async def request(self, method, host, path, body=None):
        cookie=os.getenv('ROBLOX_SESSION','').strip()
        if not cookie:
            raise RuntimeError('Configure ROBLOX_SESSION no ambiente privado.')

        if host not in (
            'games.roblox.com',
            'accountsettings.roblox.com',
            'users.roblox.com',
            'apis.roblox.com'
        ):
            raise RuntimeError('Host não autorizado.')

        headers={
            'Cookie':'.ROBLOSECURITY='+cookie,
            'Accept':'application/json'
        }

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as sess:
            for attempt in range(2):
                if self.csrf:
                    headers['X-CSRF-TOKEN']=self.csrf

                async with sess.request(
                    method,
                    'https://'+host+path,
                    json=body,
                    headers=headers,
                    allow_redirects=False
                ) as r:
                    if r.status==403 and r.headers.get('x-csrf-token') and attempt==0:
                        self.csrf=r.headers['x-csrf-token']
                        continue

                    if not 200 <= r.status < 300:
                        print(f"[ROBLOX] Etapa: {self.stage}", flush=True)
                        print(f"[ROBLOX] Metodo: {method}", flush=True)
                        print(f"[ROBLOX] Rota: {host}{path}", flush=True)
                        print(f"[ROBLOX] Status: {r.status}", flush=True)

                        self.stage=f'{self.stage} (HTTP {r.status})'
                        raise RuntimeError(f'Roblox HTTP {r.status}')

                    if r.status==204:
                        return {}

                    return await r.json()

        raise RuntimeError('Autorização Roblox não confirmada.')

    async def info(self):
        return await self.request(
            'GET',
            'games.roblox.com',
            f'/v1/vip-servers/{self.id}'
        )

    async def set_access(self,enabled):
        self.stage='consultar acesso'
        info=await self.info()

        if not isinstance(info.get('active'),bool):
            raise RuntimeError('Campo active não reconhecido; nenhuma alteração executada.')

        if info['active']!=enabled:
            self.stage='alterar acesso'

            await self.request(
                'PATCH',
                'games.roblox.com',
                f'/v1/vip-servers/{self.id}',
                {'active':enabled}
            )

        if (await self.info()).get('active') is not enabled:
            raise RuntimeError('Acesso não confirmado.')

    async def close(self):
        await self.set_access(False)

    async def open(self):
        await self.set_access(True)
        self.stage='gerar convite'
        before=await self.info()

        def code_of(data):
            for key in ('linkCode','privateServerLinkCode','joinCode'):
                value=data.get(key)
                if isinstance(value,str) and value.strip():
                    return value.strip()
            return None

        old=code_of(before)

        result=await self.request(
            'PATCH',
            'games.roblox.com',
            f'/v1/vip-servers/{self.id}',
            {'newJoinCode':True}
        )

        candidate=code_of(result)

        for delay in (0,1,2,3,4):
            if delay:
                await asyncio.sleep(delay)

            info=await self.info()
            code=code_of(info)

            if info.get('active') is not True:
                continue

            if not code or code==old:
                if candidate and candidate!=old:
                    code=candidate
                else:
                    continue

            game=info.get('game') or before.get('game') or {}

            place=(
                game.get('rootPlaceId')
                or game.get('placeId')
                or info.get('placeId')
                or info.get('rootPlaceId')
                or before.get('placeId')
            )

            # Place ID fixo do Grau SP
            place=os.getenv(
                'ROBLOX_PLACE_ID',
                '101953291486308'
            ).strip()

            if isinstance(place,str) and place.isdigit():
                place=int(place)

            if not isinstance(place,int) or isinstance(place,bool) or place<=0:
                self.stage='identificar mapa (place ID ausente)'
                raise RuntimeError('Place ID não confirmado.')

            return f'https://www.roblox.com/games/{place}?'+urlencode({
                'privateServerLinkCode':code
            })

        self.stage='confirmar novo código de convite'
        raise RuntimeError('Novo código não confirmado.')

    # Consulta individual de bloqueios - V1.6
    async def blocked(self, uid):
        self.stage='consultar bloqueio individual'
        uid=int(uid)

        data=await self.request(
            'GET',
            'apis.roblox.com',
            f'/user-blocking-api/v1/users/{uid}/is-blocked'
        )

        if isinstance(data,bool):
            print(
                f"[ROBLOX] Bloqueio consultado: {data}",
                flush=True
            )
            return data

        if isinstance(data,dict):
            for key in ('isBlocked','blocked','isUserBlocked'):
                value=data.get(key)

                if isinstance(value,bool):
                    print(
                        f"[ROBLOX] Bloqueio consultado: {value}",
                        flush=True
                    )
                    return value

            print(
                f"[ROBLOX] Campos recebidos: {list(data.keys())}",
                flush=True
            )

        raise RuntimeError(
            'Resposta de bloqueio individual não reconhecida.'
        )

    async def change_block(self,uid,block):
        uid=int(uid)

        if await self.blocked(uid)==block:
            return False

        self.stage='alterar bloqueio'
        action='block' if block else 'unblock'

        await self.request(
            'POST',
            'apis.roblox.com',
            f'/user-blocking-api/v1/users/{uid}/{action}-user',
            {}
        )

        if await self.blocked(uid)!=block:
            raise RuntimeError('Bloqueio não confirmado.')

        return True
