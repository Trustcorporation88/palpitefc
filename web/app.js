const ACEITE = "palpitefc-termo-1.0";
const ROTULOS = { casa: "Casa", empate: "Empate", fora: "Fora" };
const PAGINAS = ["rodada", "tabela", "times", "simular", "conta"];
const VERSAO = document.documentElement.dataset.versao || "";

const miolo = document.querySelector("#miolo");
const termo = document.querySelector("#termo");
const site = document.querySelector("#site");
const respostas = new Map();
let inicio = null;
let times = [];
let pedidoInicial = null;
let timeEscolhido = null;
let confronto = null;
let relogioAoVivo = null;
// Consulta já, sem esperar o relógio: chamada quando a aba volta a aparecer.
let acordarAoVivo = null;
// Sobe a cada página aberta: a resposta que chega atrasada não monta por cima da outra.
let geracao = 0;

function esc(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (letra) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[letra]);
}

function pct(valor, casas = 0) {
  if (valor == null) return "–";
  const numero = valor * 100;
  if (numero <= 0) return "–";
  if (casas === 0 && numero < 0.5) return "<1%";
  if (casas === 0 && numero >= 99.5) return ">99%";
  return `${numero.toFixed(casas).replace(".", ",")}%`;
}

function decimal(valor, casas = 3) {
  return valor == null ? "–" : valor.toFixed(casas).replace(".", ",");
}

function quando(iso) {
  const [data, hora] = iso.split("T");
  const [, mes, dia] = data.split("-");
  return `${dia}/${mes} · ${hora}`;
}

function dinheiro(valor) {
  const sinal = valor > 0 ? "+" : "";
  return `${sinal}${valor.toFixed(1).replace(".", ",")} u`;
}

function api(caminho) {
  if (!respostas.has(caminho)) {
    const separador = caminho.includes("?") ? "&" : "?";
    const pedido = fetch(`${caminho}${separador}v=${encodeURIComponent(VERSAO)}`).then((resposta) => {
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      return resposta.json();
    });
    pedido.catch(() => respostas.delete(caminho));
    respostas.set(caminho, pedido);
  }
  return respostas.get(caminho);
}

function bloco(tag, classe, html) {
  const elemento = document.createElement(tag);
  if (classe) elemento.className = classe;
  if (html != null) elemento.innerHTML = html;
  return elemento;
}

function nomeDaLeitura(jogo) {
  // Sem artigo: "do Palmeiras", mas "da Chapecoense".
  if (jogo.maisProvavel === "casa") return `${jogo.casaNome} vence`;
  if (jogo.maisProvavel === "fora") return `${jogo.foraNome} vence`;
  return "empate";
}

function plural(quantos, singular, varios) {
  return `${quantos} ${quantos === 1 ? singular : varios}`;
}

function dataCurta(iso) {
  const [, mes, dia] = iso.split("-");
  return `${dia}/${mes}`;
}

function cabecalho(jogo, rotulo) {
  // Tudo que vem do calendário passa por esc(): ele é de terceiros.
  const agenda = jogo.agenda;
  const rodada = agenda ? `${esc(agenda.rodada)}ª rodada · ` : "";
  if (jogo.quando) return `${jogo.resultado ? "" : rodada}${esc(quando(jogo.quando))}`;
  if (!agenda) return esc(rotulo);
  if (agenda.atrasado) return `${rodada}adiado, data a definir`;
  const dia = esc(dataCurta(agenda.data));
  // Sem hora, o openfootball põe na rodada inteira a data do primeiro dia.
  return agenda.hora ? `${rodada}previsto para ${dia} · ${esc(agenda.hora)}` : `${rodada}a partir de ${dia}`;
}

function cartao(jogo, rotulo = "Confronto restante") {
  const artigo = bloco("article", "jogo");
  const resultado = jogo.resultado
    ? `<b class="placar">${jogo.resultado.casa}–${jogo.resultado.fora}</b>`
    : `<span>ainda não jogou</span>`;
  const comMercado = Boolean(jogo.mercado);
  const barras = ["casa", "empate", "fora"]
    .map((mercado) => {
      const classe = mercado === jogo.maisProvavel ? "destaque" : "";
      const saiu = jogo.resultado && jogo.resultado.mercado === mercado ? " saiu" : "";
      const odd = comMercado
        ? `<div class="trilho fino" title="Odd sem margem"><i style="width:${(jogo.mercado[mercado] * 100).toFixed(1)}%"></i></div>`
        : "";
      const valorOdd = comMercado ? `<small>${pct(jogo.mercado[mercado])}</small>` : "";
      return `<div class="linha-mercado ${classe}${saiu}">
        <span>${ROTULOS[mercado]}</span>
        <div class="trilhos"><div class="trilho"><i style="width:${(jogo.chance[mercado] * 100).toFixed(1)}%"></i></div>${odd}</div>
        <span class="valor">${pct(jogo.chance[mercado])}${valorOdd}</span>
      </div>`;
    })
    .join("");

  artigo.innerHTML = `
    <header><span>${cabecalho(jogo, rotulo)}</span>${resultado}</header>
    <div class="confronto">
      <div><b>${esc(jogo.casaNome)}</b><small>${decimal(jogo.golsEsperados.casa, 2)} gols esperados</small>${faixaDaForma(jogo.forma?.casa)}</div>
      <div class="x" aria-hidden="true">×</div>
      <div><b>${esc(jogo.foraNome)}</b><small>${decimal(jogo.golsEsperados.fora, 2)} gols esperados</small>${faixaDaForma(jogo.forma?.fora)}</div>
    </div>
    <div class="barras">${barras}</div>
    ${comMercado ? `<p class="legenda"><i class="ponto modelo"></i>modelo <i class="ponto odd"></i>odd sem margem</p>` : ""}
    <div class="extra"><span>Ambos marcam ${pct(jogo.chance.ambos)}</span><span>Mais de 2,5 gols ${pct(jogo.chance.mais25)}</span></div>
    <ol class="placares" aria-label="Placares mais prováveis">
      ${jogo.placares.map((placar) => `<li>${placar.casa}–${placar.fora} · ${pct(placar.chance)}</li>`).join("")}
    </ol>`;

  const leitura = bloco("p", "leitura");
  const chance = pct(jogo.chance[jogo.maisProvavel]);
  if (jogo.resultado) {
    leitura.textContent = jogo.acertouMaisProvavel
      ? `Leitura certa no 1X2: ${nomeDaLeitura(jogo)}, ${chance}.`
      : `Leitura: ${nomeDaLeitura(jogo)}, ${chance}. Não saiu.`;
    leitura.classList.add(jogo.acertouMaisProvavel ? "ok" : "erro");
  } else {
    leitura.textContent = `Leitura: ${nomeDaLeitura(jogo)}, ${chance}. Não é palpite de aposta.`;
  }
  if (jogo.texto?.length) {
    artigo.append(bloco("p", "resumo", jogo.texto.map(esc).join(" ")));
  }
  artigo.append(leitura);
  return artigo;
}

const RESULTADOS = { V: "vitória", E: "empate", D: "derrota" };

function faixaDaForma(letras) {
  // Chega do mais recente para o mais antigo; a faixa mostra o mais recente à direita.
  if (!letras?.length) return "";
  const ordem = [...letras].reverse();
  const periodo = ordem.length === 1 ? "Último jogo na Série A" : `Últimos ${ordem.length} jogos na Série A, do mais antigo ao mais recente`;
  const descricao = `${periodo}: ${ordem.map((letra) => RESULTADOS[letra] || "").join(", ")}`;
  return `<span class="forma" role="img" aria-label="${esc(descricao)}" title="${esc(descricao)}">${ordem
    .map((letra) => `<i class="r-${esc(letra)}">${esc(letra)}</i>`)
    .join("")}</span>`;
}

function listaDaForma(forma) {
  if (!forma?.length) return "";
  const linhas = forma
    .map(
      (jogo) =>
        `<li><i class="r-${esc(jogo.resultado)}">${esc(jogo.resultado)}</i><span>${esc(quando(jogo.quando).split(" ·")[0])}/${esc(jogo.temporada.slice(2))}</span><span>${jogo.mando === "casa" ? "em casa" : "fora"} × ${esc(jogo.adversarioNome)}</span><b>${esc(jogo.golsPro)}–${esc(jogo.golsContra)}</b></li>`,
    )
    .join("");
  const titulo = forma.length === 1 ? "Último jogo na Série A" : `Últimos ${forma.length} jogos na Série A`;
  return `<h3>${titulo}</h3><ol class="lista-forma">${linhas}</ol>`;
}

function secaoConfronto(jogo) {
  const dados = jogo.confronto;
  if (!dados) return null;
  const casa = jogo.casa;
  const fora = jogo.fora;
  const total = dados.jogos;
  const largura = (valor) => (total ? ((valor / total) * 100).toFixed(1) : 0);
  const resumo = total
    ? `<p class="nota">Na Série A desde ${esc(dados.desde)}: ${total} ${total === 1 ? "jogo" : "jogos"}. Gols: ${esc(jogo.casaNome)} ${dados.gols[casa]}, ${esc(jogo.foraNome)} ${dados.gols[fora]}.</p>
      <div class="placar-confronto" role="img" aria-label="${esc(jogo.casaNome)} ${plural(dados.vitorias[casa], "vitória", "vitórias")}, ${plural(dados.empates, "empate", "empates")}, ${esc(jogo.foraNome)} ${plural(dados.vitorias[fora], "vitória", "vitórias")}">
        <i class="r-V" style="width:${largura(dados.vitorias[casa])}%"></i><i class="r-E" style="width:${largura(dados.empates)}%"></i><i class="r-D" style="width:${largura(dados.vitorias[fora])}%"></i>
      </div>
      <p class="legenda"><span>${esc(jogo.casaNome)} ${dados.vitorias[casa]}</span> · <span>empates ${dados.empates}</span> · <span>${esc(jogo.foraNome)} ${dados.vitorias[fora]}</span></p>
      <ol class="lista-forma">${dados.ultimos
        .map(
          (partida) =>
            `<li><span>${esc(quando(partida.quando).split(" ·")[0])}/${esc(partida.quando.slice(2, 4))}</span><span>${esc(partida.casaNome)} ${esc(partida.golsCasa)}–${esc(partida.golsFora)} ${esc(partida.foraNome)}</span></li>`,
        )
        .join("")}</ol>`
    : `<p class="nota">Os dois não se enfrentaram na Série A da base, que começa em ${esc(dados.inicioDaBase)}.</p>`;
  const formas = jogo.formaDetalhada || {};
  return bloco(
    "section",
    "painel",
    `<h2>Confronto direto</h2>${resumo}
    <div class="duas-colunas"><div>${listaDaForma(formas.casa).replace("<h3>", `<h3>${esc(jogo.casaNome)} · `)}</div><div>${listaDaForma(formas.fora).replace("<h3>", `<h3>${esc(jogo.foraNome)} · `)}</div></div>`,
  );
}

function heroRodada(resumo) {
  const notas = resumo.notas;
  return bloco(
    "section",
    "hero",
    `<p class="olho">Atualizado até ${quando(inicio.atualizadoEm)}</p>
    <h2>A chance do jogo, não uma aposta</h2>
    <p>Em ${resumo.jogos} jogos de ${esc(inicio.temporada)}, calculados antes do apito, a leitura mais provável acertou ${pct(resumo.taxaMaisProvavel)} e o favorito da odd acertou ${pct(resumo.taxaFavorito)}. Na nota RPS, em que menor é melhor, a odd sem margem ficou em ${decimal(notas.mercado?.rps)} e o modelo em ${decimal(notas.modelo?.rps)}. Chutar pela média dá ${decimal(notas.base?.rps)}.</p>
    <div class="numeros">
      <div class="numero"><b>${pct(resumo.taxaMaisProvavel)}</b><span>acerto da leitura</span></div>
      <div class="numero"><b>${pct(resumo.taxaFavorito)}</b><span>acerto do favorito da odd</span></div>
    </div>`,
  );
}

const FONTES = {
  "football-data.org": "Data e hora do football-data.org; a hora aparece quando a CBF confirma.",
  openfootball: "Data prevista pelo calendário do openfootball, que atrasa algumas semanas; a CBF ainda pode mudar.",
};

async function estadoAoVivo() {
  // Fora do cache de propósito: muda a cada gol. Pedido pendurado conta como falha.
  const controle = new AbortController();
  const limite = setTimeout(() => controle.abort(), 8000);
  try {
    const resposta = await fetch("/api/aovivo", { cache: "no-store", signal: controle.signal });
    return resposta.ok ? await resposta.json() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(limite);
  }
}

const EM_CAMPO = new Set(["ao vivo", "intervalo"]);
// Sem resposta do próprio site por este tempo, o placar da tela pode não ser o de agora.
const SEM_NOTICIA_MS = 3 * 60 * 1000;

function parDoJogo(jogo) {
  return `${jogo.casa}|${jogo.fora}`;
}

function horaDe(iso) {
  return iso ? iso.slice(11, 16) : "";
}

function rotuloAoVivo(jogo, hoje) {
  if (jogo.situacao === "encerrado") {
    const dia = jogo.quando?.slice(0, 10);
    return dia && hoje && dia !== hoje ? `Encerrado · ${quando(jogo.quando).split(" · ")[0]}` : "Encerrado";
  }
  if (jogo.situacao === "sem atualização") return `Sem atualização desde ${horaDe(jogo.vistoEm)}`;
  if (jogo.situacao === "intervalo") return "Intervalo";
  return jogo.minuto != null ? `Ao vivo · ${esc(jogo.minuto)}'` : "Ao vivo";
}

function mudanca(antes, agora) {
  return `${pct(antes)} → <b>${pct(agora)}</b>`;
}

function secaoSeTerminarAssim(dados, encerrados, parados) {
  if (!dados) return "";
  const zonas = [
    ["titulo", "Título"],
    ["libertadores", "G4"],
    ["rebaixamento", "Z4"],
  ];
  const maior = (time) => Math.max(...zonas.map(([zona]) => Math.abs(time.zonas[zona] - time.zonasAntes[zona])));
  const linhas = dados.times
    .filter((time) => maior(time) >= 0.02 || time.posicao !== time.posicaoAntes)
    .sort((a, b) => maior(b) - maior(a))
    .slice(0, 10)
    .map(
      (time) =>
        `<tr><td>${esc(time.nome)}</td><td>${esc(time.posicaoAntes)}º → <b>${esc(time.posicao)}º</b></td>${zonas
          .map(([zona]) => `<td>${mudanca(time.zonasAntes[zona], time.zonas[zona])}</td>`)
          .join("")}</tr>`,
    )
    .join("");
  if (!linhas) return "";
  const titulo = encerrados ? "Como fica a tabela com esses resultados" : "Se terminar assim";
  const como = encerrados
    ? "Os resultados acima ainda não estão no arquivo de resultados do site. Aqui eles já entram na classificação, e o resto do campeonato é simulado de novo."
    : "Os jogos acima entram na classificação com o placar de agora, e o resto do campeonato é simulado de novo. O jogo em andamento não ganha chance de vitória: o site não mostra números de aposta ao vivo.";
  const aviso = parados ? " Há jogo sem atualização: o placar dele pode não ser o de agora." : "";
  return `<section class="painel"><h2>${titulo}</h2>
    <p class="nota">${como}${aviso}</p>
    <div class="rolagem"><table class="tabela mudancas"><thead><tr><th>Time</th><th>Posição</th><th>Título</th><th>G4</th><th>Z4</th></tr></thead><tbody>${linhas}</tbody></table></div></section>`;
}

function htmlAoVivo(estado) {
  if (!estado?.jogos?.length) return "";
  const encerrados = estado.jogos.every((jogo) => jogo.situacao === "encerrado");
  const parados = estado.jogos.some((jogo) => jogo.situacao === "sem atualização");
  const hoje = estado.agora?.slice(0, 10);
  const cartoes = estado.jogos
    .map((jogo) => {
      const selo = jogo.situacao === "ao vivo" ? "pulsa" : jogo.situacao === "sem atualização" ? "parado" : "";
      return `<article class="jogo ao-vivo"><header><span class="selo-vivo ${selo}">${rotuloAoVivo(jogo, hoje)}</span></header>
        <div class="placar-vivo"><b>${esc(jogo.casaNome)}</b><strong>${esc(jogo.golsCasa)}–${esc(jogo.golsFora)}</strong><b>${esc(jogo.foraNome)}</b></div></article>`;
    })
    .join("");
  const fonte = estado.ultimaConsulta
    ? `<p class="nota">Placar da Bzzoiro Sports Data, consultado às ${horaDe(estado.ultimaConsulta)}.</p>`
    : "";
  return `<h2>${encerrados ? "Resultados recentes" : "Ao vivo"}</h2>${cartoes}${fonte}${secaoSeTerminarAssim(estado.seTerminarAssim, encerrados, parados)}`;
}

function semNoticia(estado) {
  // O site parou de responder: nada de "ao vivo" pulsando com o placar velho.
  return {
    ...estado,
    jogos: estado.jogos.map((jogo) =>
      EM_CAMPO.has(jogo.situacao) ? { ...jogo, situacao: "sem atualização", minuto: null, vistoEm: jogo.vistoEm || estado.ultimaConsulta } : jogo,
    ),
  };
}

function novidadesAoVivo(antes, agora) {
  // Frases curtas para o leitor de tela; o bloco ao vivo em si fica calado.
  if (!antes) return "";
  const anteriores = new Map((antes.jogos || []).map((jogo) => [parDoJogo(jogo), jogo]));
  return (agora.jogos || [])
    .map((jogo) => {
      const velho = anteriores.get(parDoJogo(jogo));
      const placar = `${jogo.casaNome} ${jogo.golsCasa}–${jogo.golsFora} ${jogo.foraNome}`;
      if (!velho) return EM_CAMPO.has(jogo.situacao) ? `Começou: ${placar}.` : "";
      const antesGols = velho.golsCasa + velho.golsFora;
      const agoraGols = jogo.golsCasa + jogo.golsFora;
      if (agoraGols > antesGols) return `Gol: ${placar}.`;
      if (agoraGols < antesGols || velho.golsCasa !== jogo.golsCasa) return `Placar corrigido: ${placar}.`;
      if (velho.situacao !== "encerrado" && jogo.situacao === "encerrado") return `Fim de jogo: ${placar}.`;
      return "";
    })
    .filter(Boolean)
    .join(" ");
}

function acompanharAoVivo(vivo, aviso, vez) {
  let html = null;
  let anterior = null;
  let ultimaBoa = 0;
  const desenhar = (atual) => {
    const novo = htmlAoVivo(atual);
    if (novo !== html) {
      // Recriar a tabela levaria a rolagem lateral de volta ao começo no celular.
      const rolagem = vivo.querySelector(".rolagem")?.scrollLeft || 0;
      vivo.innerHTML = novo;
      html = novo;
      const tabela = vivo.querySelector(".rolagem");
      if (tabela) tabela.scrollLeft = rolagem;
    }
    // Jogo que já está no ao vivo não fica também com o cartão de antes do jogo.
    const emCampo = new Set((atual?.jogos || []).map(parDoJogo));
    const cartoes = [...miolo.querySelectorAll(".jogo[data-par]")];
    cartoes.forEach((cartao) => {
      cartao.hidden = emCampo.has(cartao.dataset.par);
    });
    const vazio = cartoes.every((cartao) => cartao.hidden);
    miolo.querySelectorAll("[data-proximos]").forEach((elemento) => {
      elemento.hidden = vazio;
    });
  };
  const receber = (novo) => {
    if (novo) {
      // Servidor recém-ligado que ainda não consultou não desmente o que já se viu.
      if (novo.ativo && !novo.ultimaConsulta && anterior?.ultimaConsulta) return;
      const frase = novidadesAoVivo(anterior?.ultimaConsulta ? anterior : null, novo);
      if (frase) aviso.textContent = frase;
      anterior = novo;
      ultimaBoa = Date.now();
      desenhar(novo);
    } else if (anterior?.jogos?.length && Date.now() - ultimaBoa > SEM_NOTICIA_MS) {
      desenhar(semNoticia(anterior));
    }
  };
  const seguir = () => {
    // Só para quando o servidor diz que o ao vivo está desligado; falha de rede tenta de novo.
    if (anterior && anterior.ativo === false) return;
    // Mesmo longe do jogo a página volta a perguntar: quem abre antes do apito vê o jogo começar.
    const ligeiro = anterior?.consultando || (anterior?.jogos || []).some((jogo) => EM_CAMPO.has(jogo.situacao));
    const olhar = async () => {
      clearTimeout(relogioAoVivo);
      acordarAoVivo = null;
      if (vez !== geracao) return;
      // Aba escondida não consulta; ao voltar, acordarAoVivo consulta na hora.
      if (!document.hidden) {
        const novo = await estadoAoVivo();
        if (vez !== geracao || !vivo.isConnected) return;
        receber(novo);
      }
      seguir();
    };
    acordarAoVivo = olhar;
    relogioAoVivo = setTimeout(olhar, ligeiro ? 30000 : 90000);
  };
  return async () => {
    receber(await estadoAoVivo());
    if (vez !== geracao || !vivo.isConnected) return;
    seguir();
  };
}

async function paginaRodada(vez) {
  const vivo = bloco("div", "bloco-vivo", "");
  vivo.setAttribute("aria-live", "off");
  const aviso = bloco("p", "so-leitor", "");
  aviso.setAttribute("role", "status");
  const pedacos = [heroRodada(inicio.resumo), vivo, aviso];
  const proximos = inicio.proximos || [];
  if (proximos.length) {
    const comOdd = proximos.some((jogo) => jogo.mercado);
    const odd = comOdd
      ? `A barra azul é a chance da casa de aposta sem a margem. Quando o modelo e a odd discordam, a conferência de ${esc(inicio.temporada)} mostra que a odd costuma estar mais perto.`
      : "A chance da casa de aposta aparece quando o football-data publica as odds, às terças e sextas.";
    const titulo = bloco("h2", "", inicio.proximaRodada ? `Próxima rodada · ${esc(inicio.proximaRodada)}ª` : "Próximos jogos");
    const nota = bloco("p", "nota", `${FONTES[inicio.fonteCalendario] || "Datas e horas do football-data.co.uk."} ${odd} Não é palpite de aposta.`);
    titulo.dataset.proximos = "";
    nota.dataset.proximos = "";
    pedacos.push(titulo, nota);
    proximos.forEach((jogo) => {
      const elemento = cartao(jogo);
      elemento.dataset.par = parDoJogo(jogo);
      pedacos.push(elemento);
    });
  }
  pedacos.push(bloco("h2", "", "Última rodada"));
  inicio.rodada.forEach((jogo) => pedacos.push(cartao(jogo)));
  // A página aparece na hora; o bloco ao vivo chega quando /api/aovivo responder.
  miolo.replaceChildren(...pedacos);
  acompanharAoVivo(vivo, aviso, vez)();
}

function celulaChance(valor, tom) {
  const forca = Math.min(1, valor || 0);
  return `<td class="chance ${tom}" style="--forca:${forca.toFixed(3)}">${pct(valor)}</td>`;
}

const TONS = {
  titulo: "tom-ouro",
  libertadores: "tom-lima",
  prelibertadores: "tom-ciano",
  sulamericana: "tom-azul",
  rebaixamento: "tom-erro",
};

function zonaDaPosicao(zonas, posicao) {
  return zonas.find((zona) => zona.id !== "titulo" && posicao >= zona.de && posicao <= zona.ate);
}

function faixa(zona) {
  return zona.de === zona.ate ? `${zona.de}º` : `${zona.de}º a ${zona.ate}º`;
}

function impacto(jogo) {
  const efeitos = jogo.efeitos
    .map(
      (efeito) =>
        `<li><b>${esc(efeito.nome)}</b> · ${esc(efeito.zonaNome.toLowerCase())}: ${pct(efeito.hoje)} hoje, <span class="pos">${pct(efeito.seVencer)}</span> se vencer, <span class="neg">${pct(efeito.sePerder)}</span> se perder</li>`,
    )
    .join("");
  const rodada = jogo.agenda ? `${esc(jogo.agenda.rodada)}ª rodada · ` : "";
  return `<li class="impacto"><p><b>${esc(jogo.casaNome)} × ${esc(jogo.foraNome)}</b><small>${rodada}${pct(jogo.chance.casa)} · ${pct(jogo.chance.empate)} · ${pct(jogo.chance.fora)}</small></p><ul>${efeitos}</ul></li>`;
}

const CURVAS = [
  { chave: "titulo", rotulo: "título", classe: "ouro", chance: (linha) => linha.titulo },
  { chave: "libertadores", rotulo: "G4", classe: "modelo", chance: (linha) => linha.libertadores },
  { chave: "escapa", rotulo: "escapar do Z4", classe: "odd", chance: (linha) => 1 - linha.rebaixamento },
];

function pontosPara(curva, serie, alvo) {
  const linha = curva.find((item) => serie.chance(item) >= alvo);
  return linha ? linha.pontos : null;
}

function graficoPontos(curva) {
  const largura = 640;
  const altura = 220;
  const margem = { esquerda: 64, direita: 12, topo: 14, base: 30 };
  const menor = curva[0].pontos;
  const maior = curva.at(-1).pontos;
  const x = (pontos) => margem.esquerda + ((pontos - menor) / Math.max(1, maior - menor)) * (largura - margem.esquerda - margem.direita);
  const y = (chance) => margem.topo + (1 - chance) * (altura - margem.topo - margem.base);
  const guias = [0, 0.5, 1]
    .map(
      (chance) =>
        `<line x1="${margem.esquerda}" x2="${largura - margem.direita}" y1="${y(chance)}" y2="${y(chance)}" class="guia"/><text x="${margem.esquerda - 6}" y="${y(chance) + 4}" text-anchor="end">${Math.round(chance * 100)}%</text>`,
    )
    .join("");
  const passo = maior - menor > 40 ? 10 : 5;
  const marcas = [];
  for (let pontos = Math.ceil(menor / passo) * passo; pontos <= maior; pontos += passo) {
    marcas.push(`<text x="${x(pontos)}" y="${altura - 8}" text-anchor="middle">${pontos}</text>`);
  }
  const linhas = CURVAS.map(
    (serie) =>
      `<polyline class="serie ${serie.classe}" points="${curva.map((linha) => `${x(linha.pontos).toFixed(1)},${y(serie.chance(linha)).toFixed(1)}`).join(" ")}"/>`,
  ).join("");
  return `<svg viewBox="0 0 ${largura} ${altura}" class="grafico" role="img" aria-label="Chance de título, G4 e de escapar do Z4 para cada pontuação final">${guias}${marcas.join("")}${linhas}</svg>`;
}

function secaoPontos(curva) {
  if (!curva?.length) return null;
  const linhas = CURVAS.map((serie) => {
    const metade = pontosPara(curva, serie, 0.5);
    const quase = pontosPara(curva, serie, 0.9);
    if (metade == null) return "";
    return `<tr><td><i class="ponto ${serie.classe}"></i> ${serie.rotulo}</td><td>${metade}</td><td>${quase ?? "–"}</td></tr>`;
  }).join("");
  return bloco(
    "section",
    "painel",
    `<h2>Pontos necessários</h2>
    <p class="nota">De todos os times que terminaram com cada pontuação nas simulações, quantos foram campeões, ficaram no G4 ou escaparam do Z4. Vale para o campeonato como ele está hoje.</p>
    ${graficoPontos(curva)}
    <p class="legenda">${CURVAS.map((serie) => `<i class="ponto ${serie.classe}"></i>${serie.rotulo}`).join(" ")}</p>
    <table class="tabela notas"><thead><tr><th>Objetivo</th><th>50% de chance</th><th>90% de chance</th></tr></thead><tbody>${linhas}</tbody></table>`,
  );
}

function secaoImpacto(dados) {
  const proxima = dados.impactoProximaRodada || [];
  const naProxima = new Set(proxima.map((jogo) => `${jogo.casa}|${jogo.fora}`));
  const resto = (dados.impacto || []).filter((jogo) => !naProxima.has(`${jogo.casa}|${jogo.fora}`));
  const blocoProxima = proxima.length
    ? `<h3>Na próxima rodada${dados.proximaRodada ? ` (${esc(dados.proximaRodada)}ª)` : ""}</h3><ol class="impactos">${proxima.slice(0, 5).map(impacto).join("")}</ol><h3>No resto do campeonato</h3>`
    : "";
  return bloco(
    "section",
    "painel",
    `<h2>Jogos que mais mexem na tabela</h2>
    <p class="nota">Compara as simulações em que cada time venceu com as que ele perdeu, do maior efeito para o menor.</p>
    ${blocoProxima}<ol class="impactos">${resto.slice(0, 8).map(impacto).join("")}</ol>`,
  );
}

async function paginaTabela() {
  const [dados, forca] = await Promise.all([api("/api/tabela"), api("/api/forca")]);
  const zonas = dados.zonas;
  const classificacao = dados.times
    .map((time) => {
      const zona = zonaDaPosicao(zonas, time.posicao);
      const marca = zona ? TONS[zona.id] : "";
      return `<tr><td class="pos ${marca}">${time.posicao}</td><td>${esc(time.nome)}</td><td><b>${time.pts}</b></td><td>${time.j}</td><td>${time.v}</td><td>${time.sg > 0 ? "+" : ""}${time.sg}</td></tr>`;
    })
    .join("");
  const chances = dados.times
    .map(
      (time) =>
        `<tr><td>${esc(time.nome)}</td><td>${decimal(time.pontosEsperados, 0)}<small> (${time.pontosFaixa[0]}–${time.pontosFaixa[1]})</small></td>${zonas
          .map((zona) => celulaChance(time.zonas[zona.id], TONS[zona.id]))
          .join("")}</tr>`,
    )
    .join("");
  const linhasForca = forca.times
    .map((time) => {
      const ataque = time.ataque * 100;
      const defesa = time.defesa * 100;
      return `<tr><td>${esc(time.nome)}</td><td class="${ataque >= 0 ? "pos" : "neg"}">${ataque >= 0 ? "+" : ""}${ataque.toFixed(0)}%</td><td class="${defesa <= 0 ? "pos" : "neg"}">${defesa >= 0 ? "+" : ""}${defesa.toFixed(0)}%</td></tr>`;
    })
    .join("");

  miolo.replaceChildren(
    bloco(
      "section",
      "painel",
      `<h2>Classificação</h2>
      <p class="nota">Jogos até ${quando(dados.atualizadoEm)}. Desempate: pontos, vitórias, saldo e gols marcados.</p>
      <table class="tabela"><thead><tr><th>#</th><th>Time</th><th>Pts</th><th>J</th><th>V</th><th>SG</th></tr></thead><tbody>${classificacao}</tbody></table>
      <p class="legenda-zonas">${zonas
        .filter((zona) => zona.id !== "titulo")
        .map((zona) => `<span><i class="ponto ${TONS[zona.id]}"></i>${esc(zona.nome)} (${faixa(zona)})</span>`)
        .join("")}</p>`,
    ),
    bloco(
      "section",
      "painel",
      `<h2>Chance no fim do campeonato</h2>
      <p class="nota">Os ${dados.jogosRestantes} jogos que faltam foram sorteados ${dados.simulacoes.toLocaleString("pt-BR")} vezes com a mesma tabela de placares do modelo. ${dados.variantes > 1 ? `A força de cada time não é conhecida com exatidão, então cada bloco de ${Math.round(dados.simulacoes / dados.variantes)} temporadas usa uma de ${dados.variantes} versões do modelo sorteadas dentro dessa incerteza. ` : ""}A faixa de pontos vale para 90% das simulações. As vagas seguem a regra de ${esc(dados.regraDasVagas)} pela posição; a CBF passa a vaga adiante quando um campeão de copa já está classificado.</p>
      <div class="rolagem"><table class="tabela chances"><thead><tr><th>Time</th><th>Pts no fim</th>${zonas
        .map((zona) => `<th title="${esc(zona.nome)} (${faixa(zona)})">${esc(zona.curto)}</th>`)
        .join("")}</tr></thead><tbody>${chances}</tbody></table></div>`,
    ),
    ...[secaoPontos(dados.pontosNecessarios), secaoImpacto(dados)].filter(Boolean),
    bloco(
      "section",
      "painel",
      `<h2>Força no campeonato</h2>
      <p class="nota">Ataque é quanto o time marca a mais que a média. Defesa é quanto ele sofre a mais: número negativo é defesa boa. O mando de campo entra à parte, em todo jogo.</p>
      <table class="tabela forca"><thead><tr><th>Time</th><th>Ataque</th><th>Defesa</th></tr></thead><tbody>${linhasForca}</tbody></table>`,
    ),
  );
}

function seletor(rotulo, id, escolhido) {
  const opcoes = times
    .map((time) => `<option value="${esc(time.id)}"${time.id === escolhido ? " selected" : ""}>${esc(time.nome)}</option>`)
    .join("");
  return `<label class="campo">${rotulo}<select id="${id}">${opcoes}</select></label>`;
}

function resumoDoTime(linha, zonas) {
  if (!linha) return "";
  const maior = Math.max(...linha.posicoes);
  const barras = linha.posicoes
    .map((chance, posicao) => {
      const zona = zonaDaPosicao(zonas, posicao + 1);
      const altura = chance > 0 ? Math.max(3, (chance / maior) * 100) : 0;
      return `<div class="coluna ${zona ? TONS[zona.id] : ""}" title="${posicao + 1}º: ${pct(chance, 1)}"><i style="height:${altura.toFixed(1)}%"></i><span>${posicao + 1}</span></div>`;
    })
    .join("");
  return `
    <div class="numeros tres">
      <div class="numero"><b>${linha.posicao}º</b><span>${linha.pts} pontos em ${linha.j} jogos</span></div>
      <div class="numero"><b>${decimal(linha.pontosEsperados, 0)}</b><span>pontos esperados no fim</span></div>
      <div class="numero"><b>${pct(linha.zonas.rebaixamento)}</b><span>chance de cair</span></div>
    </div>
    <p class="nota">${zonas
      .filter((zona) => zona.id !== "rebaixamento")
      .map((zona) => `${esc(zona.nome)} ${pct(linha.zonas[zona.id])}`)
      .join(" · ")}</p>
    <div class="distribuicao" role="img" aria-label="Chance de terminar em cada posição">${barras}</div>
    <p class="nota pequeno">Chance de terminar em cada posição, do 1º ao 20º.</p>`;
}

async function paginaTimes() {
  if (!timeEscolhido) timeEscolhido = times[0]?.id;
  const painelEl = bloco(
    "section",
    "painel",
    `<h2>Time a time</h2>
    <p class="nota">Os ${inicio.restantes} jogos que faltam no turno e returno, com a chance de hoje. Não há odd futura nesta base, então não há comparação com a casa de aposta.</p>
    ${seletor("Time", "escolha-time", timeEscolhido)}
    <div id="resumo-time"></div>`,
  );
  const lista = bloco("div", "");
  miolo.replaceChildren(painelEl, lista);
  const select = painelEl.querySelector("select");
  const tabela = await api("/api/tabela");
  const carregar = async () => {
    timeEscolhido = select.value;
    const dados = await api(`/api/time/${encodeURIComponent(select.value)}`);
    painelEl.querySelector("#resumo-time").innerHTML = resumoDoTime(dados.tabela, tabela.zonas) + listaDaForma(dados.forma);
    lista.replaceChildren(...dados.jogos.map((jogo) => cartao(jogo)));
  };
  select.addEventListener("change", carregar);
  await carregar();
}

function gradeDePlacares(jogo) {
  const maior = Math.max(...jogo.grade.flat());
  const cabeca = jogo.grade[0].map((_, coluna) => `<th>${coluna}</th>`).join("");
  const linhas = jogo.grade
    .map(
      (linha, golsCasa) =>
        `<tr><th>${golsCasa}</th>${linha
          .map((chance) => `<td style="--forca:${(chance / maior).toFixed(3)}">${pct(chance, 1)}</td>`)
          .join("")}</tr>`,
    )
    .join("");
  return `<div class="rolagem"><table class="grade" aria-label="Chance de cada placar">
    <caption>Linhas: gols do ${esc(jogo.casaNome)} · colunas: gols do ${esc(jogo.foraNome)}</caption>
    <thead><tr><th></th>${cabeca}</tr></thead><tbody>${linhas}</tbody></table></div>`;
}

async function paginaSimular() {
  if (!confronto) confronto = { casa: times[0]?.id, fora: times[1]?.id };
  const painelEl = bloco(
    "section",
    "painel",
    `<h2>Simular um confronto</h2>
    <p class="nota">Escolha quem joga em casa e quem visita. A chance usa a força de hoje e o mando de campo.</p>
    <div class="dupla">${seletor("Mandante", "sim-casa", confronto.casa)}<button type="button" class="trocar" aria-label="Inverter mando">⇄</button>${seletor("Visitante", "sim-fora", confronto.fora)}</div>`,
  );
  const saida = bloco("div", "");
  miolo.replaceChildren(painelEl, saida);
  const casa = painelEl.querySelector("#sim-casa");
  const fora = painelEl.querySelector("#sim-fora");
  const calcular = async () => {
    confronto = { casa: casa.value, fora: fora.value };
    if (casa.value === fora.value) {
      saida.replaceChildren(bloco("p", "vazio", "Escolha dois times diferentes."));
      return;
    }
    const jogo = await api(`/api/simular?casa=${encodeURIComponent(casa.value)}&fora=${encodeURIComponent(fora.value)}`);
    const extra = bloco(
      "section",
      "painel",
      `<h2>Placar a placar</h2>${gradeDePlacares(jogo)}
      <div class="numeros tres">
        <div class="numero"><b>${pct(jogo.chance.mais15)}</b><span>mais de 1,5 gols</span></div>
        <div class="numero"><b>${pct(jogo.chance.mais25)}</b><span>mais de 2,5 gols</span></div>
        <div class="numero"><b>${pct(jogo.chance.mais35)}</b><span>mais de 3,5 gols</span></div>
      </div>`,
    );
    saida.replaceChildren(...[cartao(jogo, "Simulação com a força de hoje"), extra, secaoConfronto(jogo)].filter(Boolean));
  };
  casa.addEventListener("change", calcular);
  fora.addEventListener("change", calcular);
  painelEl.querySelector(".trocar").addEventListener("click", () => {
    [casa.value, fora.value] = [fora.value, casa.value];
    calcular();
  });
  await calcular();
}

function graficoLinhas(serie) {
  const largura = 640;
  const altura = 220;
  const margem = { esquerda: 64, direita: 12, topo: 14, base: 30 };
  const valores = serie.flatMap((ponto) => [ponto.modelo, ponto.mercado]).filter((valor) => valor != null);
  const minimo = Math.min(...valores) - 0.004;
  const maximo = Math.max(...valores) + 0.004;
  const x = (indice) => margem.esquerda + (indice / Math.max(1, serie.length - 1)) * (largura - margem.esquerda - margem.direita);
  const y = (valor) => margem.topo + (1 - (valor - minimo) / (maximo - minimo)) * (altura - margem.topo - margem.base);
  const caminho = (chave) =>
    serie
      .map((ponto, indice) => (ponto[chave] == null ? null : `${x(indice).toFixed(1)},${y(ponto[chave]).toFixed(1)}`))
      .filter(Boolean)
      .join(" ");
  const marcas = [minimo + 0.004, (minimo + maximo) / 2, maximo - 0.004]
    .map(
      (valor) =>
        `<line x1="${margem.esquerda}" x2="${largura - margem.direita}" y1="${y(valor)}" y2="${y(valor)}" class="guia"/><text x="${margem.esquerda - 6}" y="${y(valor) + 4}" text-anchor="end">${decimal(valor)}</text>`,
    )
    .join("");
  const ultimo = serie.at(-1);
  return `<svg viewBox="0 0 ${largura} ${altura}" class="grafico" role="img" aria-label="RPS acumulado na temporada: modelo ${decimal(ultimo.modelo)}, odd sem margem ${decimal(ultimo.mercado)}">
    ${marcas}
    <text x="${margem.esquerda}" y="${altura - 8}">${quando(serie[0].inicio).split(" ·")[0]}</text>
    <text x="${largura - margem.direita}" y="${altura - 8}" text-anchor="end">${quando(ultimo.inicio).split(" ·")[0]}</text>
    <polyline points="${caminho("mercado")}" class="serie odd"/>
    <polyline points="${caminho("modelo")}" class="serie modelo"/>
  </svg>`;
}

function graficoCalibracao(calibracao) {
  const lado = 300;
  const margem = 34;
  const folga = 10;
  const util = lado - margem - folga;
  const escala = (valor) => margem + valor * util;
  const inverter = (valor) => lado - margem - valor * util;
  const rotulo = (valor) => `${Math.round(valor * 100)}%`;
  const pontos = (linhas, classe) =>
    `<polyline class="serie ${classe}" points="${linhas.map((linha) => `${escala(linha.prevista).toFixed(1)},${inverter(linha.observada).toFixed(1)}`).join(" ")}"/>` +
    linhas
      .map(
        (linha) =>
          `<circle class="${classe}" cx="${escala(linha.prevista).toFixed(1)}" cy="${inverter(linha.observada).toFixed(1)}" r="${Math.min(7, 2 + Math.sqrt(linha.casos) / 4).toFixed(1)}"><title>Previsto ${pct(linha.prevista)}, aconteceu ${pct(linha.observada)} (${linha.casos} casos)</title></circle>`,
      )
      .join("");
  const marcas = [0, 0.25, 0.5, 0.75, 1]
    .map(
      (valor) =>
        `<text x="${escala(valor)}" y="${lado - margem + 18}" text-anchor="middle">${rotulo(valor)}</text><text x="${margem - 6}" y="${inverter(valor) + 4}" text-anchor="end">${rotulo(valor)}</text>`,
    )
    .join("");
  return `<svg viewBox="0 0 ${lado} ${lado}" class="grafico quadrado" role="img" aria-label="Calibração: chance prevista contra frequência observada">
    <line class="diagonal" x1="${escala(0)}" y1="${inverter(0)}" x2="${escala(1)}" y2="${inverter(1)}"/>
    ${marcas}
    ${pontos(calibracao.mercado, "odd")}
    ${pontos(calibracao.modelo, "modelo")}
  </svg>`;
}

function diferenca(dados) {
  if (!dados) return "";
  const [baixo, alto] = dados.ic95;
  const quem = dados.media > 0 ? "a odd foi melhor" : "o modelo foi melhor";
  const certeza =
    baixo > 0 || alto < 0
      ? "A diferença não se explica por sorte na amostra."
      : "Com esse número de jogos, a diferença ainda pode ser sorte.";
  return `<p class="nota">Jogo a jogo, ${quem} por ${decimal(Math.abs(dados.media), 4)} de RPS (intervalo de 95%: ${decimal(baixo, 4)} a ${decimal(alto, 4)}). ${certeza}</p>`;
}

function lista(itens) {
  return itens.length < 2 ? itens.join("") : `${itens.slice(0, -1).join(", ")} e ${itens.at(-1)}`;
}

function secaoConferenciaTabela(conferencia) {
  if (!conferencia) return null;
  const prova = conferencia.prova;
  const escala = conferencia.melhorChave;
  const comIncerteza = prova[escala];
  const semIncerteza = prova["0.0"];
  const hoje = prova["tabela de hoje"];
  if (!comIncerteza || !semIncerteza || !hoje) return null;
  const linha = (rotulo, notas) =>
    `<tr><td>${rotulo}</td><td>${decimal(notas.rps, 4)}</td><td>${decimal(notas.titulo, 3)}</td><td>${decimal(notas.libertadores, 3)}</td><td>${decimal(notas.rebaixamento, 3)}</td></tr>`;
  const zonas = { titulo: "título", libertadores: "G4", rebaixamento: "Z4" };
  // Diferença menor que meio milésimo de Brier é empate, não melhora nem piora.
  const limiar = 0.0005;
  const efeito = (zona) => comIncerteza[zona] - semIncerteza[zona];
  const melhora = Object.keys(zonas).filter((zona) => efeito(zona) < -limiar).map((zona) => zonas[zona]);
  const piora = Object.keys(zonas).filter((zona) => efeito(zona) > limiar).map((zona) => zonas[zona]);
  const empata = Object.keys(zonas).filter((zona) => Math.abs(efeito(zona)) <= limiar).map((zona) => zonas[zona]);
  const anos = conferencia.config.temporadasDeProva;
  const anosEscolha = conferencia.config.temporadasDeEscolha;
  return bloco(
    "section",
    "painel",
    `<h2>A tabela simulada, conferida</h2>
    <p class="nota">Em cada temporada de ${anos[0]} a ${anos.at(-1)}, o modelo foi ajustado só com o que havia depois de ${lista(conferencia.config.rodadasDeCorte.map(String))} rodadas, o resto do campeonato foi simulado e a chance de cada posição foi comparada com a classificação final de verdade. Menor é melhor.</p>
    <div class="rolagem"><table class="tabela notas"><thead><tr><th>Previsão</th><th>RPS da posição</th><th>Brier título</th><th>Brier G4</th><th>Brier Z4</th></tr></thead><tbody>
      ${linha(`Com incerteza (escala ${esc(escala.replace(".", ","))})`, comIncerteza)}
      ${linha("Sem incerteza", semIncerteza)}
      ${linha("Tabela de hoje fica como está", hoje)}
    </tbody></table></div>
    <p class="nota">A escala da incerteza foi escolhida em ${anosEscolha[0]}–${anosEscolha.at(-1)}. Na prova, ela ${comIncerteza.rps < semIncerteza.rps ? "melhora" : "não melhora"} o RPS da posição${melhora.length ? ` e o Brier ${lista(melhora.map((zona) => `do ${zona}`))}` : ""}${empata.length ? `; ${lista(empata.map((zona) => `no ${zona}`))}, fica igual` : ""}${piora.length ? `; ${lista(piora.map((zona) => `no ${zona}`))}, piora um pouco` : ""}.</p>`,
  );
}

async function paginaConta() {
  const dados = await api("/api/conta");
  const resumo = dados.resumo;
  const notas = resumo.notas;
  const config = dados.config || {};
  const linhaNota = (rotulo, nota) =>
    `<tr><td>${rotulo}</td><td>${decimal(nota?.rps)}</td><td>${decimal(nota?.brier)}</td><td>${decimal(nota?.logLoss)}</td></tr>`;
  miolo.replaceChildren(
    bloco(
      "section",
      "painel",
      `<h2>O que a conta fez em ${esc(dados.temporada)}</h2>
      <p class="nota">Cada jogo foi calculado só com o que já tinha acontecido. O modelo é o Dixon-Coles: gols de cada time, mando de campo e mais peso para o jogo recente. Todos os mercados saem da mesma tabela de placares.</p>
      <table class="tabela notas"><thead><tr><th>Previsão</th><th>RPS</th><th>Brier</th><th>Log loss</th></tr></thead><tbody>
        ${linhaNota("Odd sem margem", notas.mercado)}
        ${linhaNota("Modelo", notas.modeloMesmosJogos)}
        ${linhaNota("Média da liga", notas.base)}
      </tbody></table>
      <p class="nota">Menor é melhor nas três notas. O RPS é a nota padrão do futebol porque leva a ordem em conta: dar o empate quando a casa vence erra menos do que dar o visitante. A odd de fechamento é o adversário mais difícil que existe; o modelo teve nota melhor do que ela em ${notas.jogosModeloMelhor} dos ${notas.jogosComMercado} jogos.</p>
      ${diferenca(notas.diferencaRps)}
      <p class="nota pequeno">Para comparar: no Brasileirão 2021, um estudo da FGV mediu RPS de 0,205 para a casa de aposta, 0,205 para o FiveThirtyEight, 0,210 para o Chance de Gol e 0,218 para o modelo da UFMG.</p>`,
    ),
    bloco(
      "section",
      "painel",
      `<h2>RPS acumulado na temporada</h2>
      <p class="nota">Cada ponto fecha um bloco de jogos sem pausa de mais de 36 horas. Quanto mais baixo, melhor.</p>
      ${graficoLinhas(dados.serie)}
      <p class="legenda"><i class="ponto modelo"></i>modelo <i class="ponto odd"></i>odd sem margem</p>`,
    ),
    bloco(
      "section",
      "painel",
      `<h2>Calibração</h2>
      <p class="nota">Quando a conta diz 40%, o resultado precisa acontecer perto de 4 vezes em 10. Ponto em cima da linha tracejada é chance bem calibrada.</p>
      ${graficoCalibracao(resumo.calibracao)}
      <p class="legenda"><i class="ponto modelo"></i>modelo <i class="ponto odd"></i>odd sem margem · tamanho do ponto = número de casos</p>`,
    ),
    bloco(
      "section",
      "painel",
      `<h2>Acerto e dinheiro</h2>
      <div class="numeros">
        <div class="numero"><b>${resumo.jogos}</b><span>jogos conferidos</span></div>
        <div class="numero"><b>${resumo.acertosMaisProvavel}</b><span>leituras certas no 1X2</span></div>
        <div class="numero"><b>${pct(resumo.taxaFavorito)}</b><span>favorito da odd</span></div>
        <div class="numero"><b>${dinheiro(resumo.lucroFavorito)}</b><span>seguir a odd, 1 unidade</span></div>
        <div class="numero"><b>${resumo.palpites}</b><span>vantagens que seriam marcadas</span></div>
        <div class="numero"><b>${dinheiro(resumo.lucroPalpite)}</b><span>seguir a vantagem</span></div>
      </div>
      <p class="nota">A vantagem seria marcada quando a chance do modelo, na odd média, prometesse mais de 3% de retorno. Ela acertou ${pct(resumo.taxaPalpite)} e perdeu dinheiro. A odd favorita também perde, porque a casa fica com a margem, mas perde menos. Por isso o site mostra a chance e não marca aposta.</p>
      <p class="nota">Um acerto passado não vale para o próximo jogo. Toda combinação continua incerta.</p>`,
    ),
    ...[secaoConferenciaTabela(dados.tabela)].filter(Boolean),
    bloco(
      "section",
      "painel",
      `<h2>Como o modelo foi regulado</h2>
      <p class="nota">Peso do jogo antigo: cai ${decimal((1 - Math.exp(-(config.xi || 0) * 365)) * 100, 0)}% por ano (xi = ${String(config.xi).replace(".", ",")}). Puxão para a média: ${config.l2}, que segura o time com poucos jogos na base. O time que subiu da Série B é puxado para um nível um pouco abaixo da média (${String(config.promovido ?? 0).replace(".", ",")} no ataque e na defesa, na escala do modelo), e não para a média. Janela: ${config.janelaDias} dias. Os três números foram escolhidos pelo menor RPS em 2024 e 2025; 2026 ficou de fora da escolha e serve de prova. A odd perde a margem pelo método de Shin.</p>
      ${dados.simulacao?.variantes > 1 ? `<p class="nota">Na tabela simulada, a incerteza da força de cada time entra por ${dados.simulacao.variantes} versões do modelo sorteadas da covariância dos parâmetros, com escala ${String(dados.simulacao.escalaIncerteza).replace(".", ",")}.</p>` : ""}
      <p class="nota pequeno">Conta gerada em ${esc(dados.geradoEm.replace("T", " "))}.</p>`,
    ),
  );
}

const MONTAR = {
  rodada: paginaRodada,
  tabela: paginaTabela,
  times: paginaTimes,
  simular: paginaSimular,
  conta: paginaConta,
};

function rotaAtual() {
  const nome = location.hash.replace("#", "");
  return PAGINAS.includes(nome) ? nome : "rodada";
}

async function abrir(nome) {
  const vez = ++geracao;
  clearTimeout(relogioAoVivo);
  relogioAoVivo = null;
  acordarAoVivo = null;
  document.querySelectorAll(".menu button").forEach((botao) => {
    const ativa = botao.dataset.pag === nome;
    botao.classList.toggle("ativa", ativa);
    if (ativa) botao.setAttribute("aria-current", "page");
    else botao.removeAttribute("aria-current");
  });
  miolo.replaceChildren(bloco("p", "vazio", "Carregando..."));
  try {
    await dadosProntos();
    // Outra página foi pedida enquanto os dados não vinham.
    if (vez !== geracao) return;
    await MONTAR[nome](vez);
  } catch (erro) {
    const aviso = bloco("div", "painel", `<p class="vazio">Não deu para carregar agora. Confira a conexão e tente de novo.</p><button type="button" class="botao">Tentar de novo</button>`);
    aviso.querySelector("button").addEventListener("click", () => abrir(nome));
    miolo.replaceChildren(aviso);
    console.error(erro);
  }
  window.scrollTo({ top: 0 });
}

function liberar() {
  termo.hidden = true;
  site.hidden = false;
}

function lerAceite() {
  try {
    return localStorage.getItem(ACEITE);
  } catch {
    return null;
  }
}

function gravarAceite() {
  try {
    localStorage.setItem(ACEITE, new Date().toISOString());
  } catch {
    // Sem armazenamento, o termo volta na próxima visita.
  }
}

document.querySelectorAll("#form-termo input").forEach((caixa) => {
  caixa.addEventListener("change", () => {
    const marcadas = [...document.querySelectorAll("#form-termo input")].every((item) => item.checked);
    document.querySelector("#aceitar").disabled = !marcadas;
  });
});

document.querySelector("#form-termo").addEventListener("submit", (evento) => {
  evento.preventDefault();
  gravarAceite();
  liberar();
  abrir(rotaAtual());
});

document.querySelectorAll(".menu button").forEach((botao) => {
  botao.addEventListener("click", () => {
    if (rotaAtual() === botao.dataset.pag) abrir(botao.dataset.pag);
    else location.hash = botao.dataset.pag;
  });
});

window.addEventListener("hashchange", () => {
  if (!site.hidden) abrir(rotaAtual());
});

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && acordarAoVivo) acordarAoVivo();
});

function dadosProntos() {
  // Se o pedido falhar (deploy reiniciando, rede ruim), o próximo "Tentar de novo" pede outra vez.
  if (!pedidoInicial) {
    pedidoInicial = Promise.all([api("/api/inicio"), api("/api/times").then((dados) => dados.times)])
      .then(([painelInicial, listaTimes]) => {
        inicio = painelInicial;
        document.querySelector("#competicao").textContent = inicio.competicao;
        times = listaTimes;
      })
      .catch((erro) => {
        pedidoInicial = null;
        throw erro;
      });
  }
  return pedidoInicial;
}

if (lerAceite()) {
  liberar();
  abrir(rotaAtual());
} else {
  termo.hidden = false;
}
