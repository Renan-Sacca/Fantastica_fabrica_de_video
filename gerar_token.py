import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Os escopos necessários para ler, criar e editar arquivos no Drive.
SCOPES = ['https://www.googleapis.com/auth/drive']

def main():
    """Autentica o usuário e salva o token.json."""
    creds = None
    
    # O token.json guarda o token de acesso e de atualização do usuário.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
    # Se não há credenciais válidas, permite que o usuário faça o login.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                print("\n[ERRO] O arquivo 'credentials.json' não foi encontrado na raiz.")
                print("Por favor, baixe o arquivo de credenciais OAuth 2.0 (Client ID) do Google Cloud Console e coloque-o nesta pasta.")
                return
                
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            
            print("\nIniciando servidor local para autenticação...")
            print("Uma janela do navegador será aberta. Faça login com a conta dos 5TB.")
            creds = flow.run_local_server(port=0)
            
        # Salva as credenciais para as próximas rodadas
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    print("\n[SUCESSO] O arquivo 'token.json' foi gerado e as credenciais são válidas!")
    print("Você pode copiar 'credentials.json' e 'token.json' para o servidor VPN/VPS.")

if __name__ == '__main__':
    main()
