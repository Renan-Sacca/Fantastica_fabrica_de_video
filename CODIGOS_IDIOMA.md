# 🌍 Códigos de Idioma Suportados

## 📋 Formato

Os códigos de idioma seguem o padrão **ISO 639-1 + ISO 3166-1**:
- **Formato:** `idioma-PAÍS`
- **Exemplo:** `pt-BR` (Português do Brasil)

---

## 🔤 Principais Idiomas

### Português
- `pt-BR` - Português do Brasil 🇧🇷
- `pt-PT` - Português de Portugal 🇵🇹

### Inglês
- `en-US` - Inglês americano 🇺🇸
- `en-GB` - Inglês britânico 🇬🇧
- `en-AU` - Inglês australiano 🇦🇺
- `en-CA` - Inglês canadense 🇨🇦
- `en-IN` - Inglês indiano 🇮🇳

### Espanhol
- `es-ES` - Espanhol da Espanha 🇪🇸
- `es-MX` - Espanhol do México 🇲🇽
- `es-AR` - Espanhol da Argentina 🇦🇷
- `es-CO` - Espanhol da Colômbia 🇨🇴
- `es-CL` - Espanhol do Chile 🇨🇱

### Francês
- `fr-FR` - Francês da França 🇫🇷
- `fr-CA` - Francês canadense 🇨🇦
- `fr-BE` - Francês da Bélgica 🇧🇪
- `fr-CH` - Francês da Suíça 🇨🇭

### Alemão
- `de-DE` - Alemão da Alemanha 🇩🇪
- `de-AT` - Alemão da Áustria 🇦🇹
- `de-CH` - Alemão da Suíça 🇨🇭

### Italiano
- `it-IT` - Italiano da Itália 🇮🇹
- `it-CH` - Italiano da Suíça 🇨🇭

### Chinês
- `zh-CN` - Chinês simplificado (China) 🇨🇳
- `zh-TW` - Chinês tradicional (Taiwan) 🇹🇼
- `zh-HK` - Chinês tradicional (Hong Kong) 🇭🇰

### Japonês
- `ja-JP` - Japonês 🇯🇵

### Coreano
- `ko-KR` - Coreano 🇰🇷

### Russo
- `ru-RU` - Russo 🇷🇺

### Árabe
- `ar-SA` - Árabe (Arábia Saudita) 🇸🇦
- `ar-EG` - Árabe (Egito) 🇪🇬
- `ar-AE` - Árabe (Emirados Árabes) 🇦🇪

### Hindi
- `hi-IN` - Hindi 🇮🇳

### Turco
- `tr-TR` - Turco 🇹🇷

### Polonês
- `pl-PL` - Polonês 🇵🇱

### Holandês
- `nl-NL` - Holandês (Holanda) 🇳🇱
- `nl-BE` - Holandês (Bélgica) 🇧🇪

### Sueco
- `sv-SE` - Sueco 🇸🇪

### Norueguês
- `no-NO` - Norueguês 🇳🇴

### Dinamarquês
- `da-DK` - Dinamarquês 🇩🇰

### Finlandês
- `fi-FI` - Finlandês 🇫🇮

### Grego
- `el-GR` - Grego 🇬🇷

### Hebraico
- `he-IL` - Hebraico 🇮🇱

### Tailandês
- `th-TH` - Tailandês 🇹🇭

### Vietnamita
- `vi-VN` - Vietnamita 🇻🇳

### Indonésio
- `id-ID` - Indonésio 🇮🇩

### Malaio
- `ms-MY` - Malaio 🇲🇾

### Filipino
- `fil-PH` - Filipino (Tagalog) 🇵🇭

---

## 🎯 Uso Recomendado

### Auto-detecção (Recomendado)
```
language_id: (vazio)
```
O sistema detecta automaticamente o idioma do texto.

### Forçar Idioma
```
language_id: pt-BR
```
Força o uso de português brasileiro, útil para:
- Garantir sotaque específico
- Textos multilíngues
- Pronúncia correta de nomes

### Quando Usar
- ✅ **Textos mistos** - Quando há palavras em vários idiomas
- ✅ **Sotaques específicos** - Para diferenciar pt-BR de pt-PT
- ✅ **Nomes próprios** - Para pronúncia correta
- ❌ **Textos simples** - Deixe auto-detectar (funciona bem)

---

## 💡 Exemplos Práticos

### Português do Brasil
```json
{
  "text": "Olá, como vai? Hoje está um dia lindo!",
  "language_id": "pt-BR"
}
```

### Inglês Americano vs Britânico
```json
// Americano
{
  "text": "Hello, how are you?",
  "language_id": "en-US"
}

// Britânico
{
  "text": "Hello, how are you?",
  "language_id": "en-GB"
}
```

### Texto Multilíngue
```json
{
  "text": "Welcome to Brasil! Bem-vindo ao nosso país!",
  "language_id": "pt-BR"
}
```

---

## 📝 Notas Importantes

1. **Case-sensitive:** Use `pt-BR`, não `pt-br` ou `PT-BR`
2. **Hífen obrigatório:** Use `pt-BR`, não `pt_BR` ou `ptBR`
3. **Auto-detecção funciona bem:** Na maioria dos casos, deixe vazio
4. **Sotaque vs Idioma:** O código afeta pronúncia e sotaque
5. **600+ idiomas suportados:** Lista acima mostra os principais

---

## 🔍 Referências

- **ISO 639-1:** Códigos de idioma (2 letras)
- **ISO 3166-1:** Códigos de país (2 letras)
- **IETF BCP 47:** Padrão completo de tags de idioma

---

**OmniVoice suporta 600+ idiomas!** 🌍

A lista acima mostra apenas os mais comuns. O sistema pode sintetizar praticamente qualquer idioma.

---

**Data:** 01/07/2026  
**Atualizado:** Corrigido formato de códigos de idioma
