const ACEITE = "palpitefc-termo-1.0";
const ROTULOS = { casa: "Casa", empate: "Empate", fora: "Fora" };

const miolo = document.querySelector("#miolo");
const termo = document.querySelector("#termo");
const site = document.querySelector("#site");
let pagina = "rodada";
let inicio = null;
let times = [];

function pct(valor) {
  return `${Math.round(valor * 100)}%`;
}

function quando(iso) {
  const [data, hora] = iso.split("T");
  const [ano, mes, dia] = data.split("-");
  return `${dia}/${mes} · ${hora}`;
}

function dinheiro(valor) {
  const sinal = valor > 0 ? "+" : "";
  return `${sinal}${valor.toFixed(1).replace(".", ",")} u`;
}

function cartao(jogo) {
  const artigo = document.createElement("article");
  artigo.className = "jogo";
  const resultado = jogo.resultado
    ? `<b class="placar">${jogo.resultado.casa}–${jogo.resultado.fora}</b>`
    : `<span>ainda não jogou</span>`;
  const leitura = document.createElement("p");
  leitura.className = "leitura";
  const nomeLeitura =
    jogo.maisProvavel === "casa"
      ? `vitória do ${jogo.casaNome}`
      : jogo.maisProvavel === "fora"
        ? `vitória do ${jogo.foraNome}`
        : "empate";
  if (jogo.resultado) {
    leitura.textContent = jogo.acertouMaisProvavel
      ? `A leitura (${nomeLeitura}, ${pct(jogo.chance[jogo.maisProvavel])}) acertou o 1X2.`
      : `A leitura era ${nomeLeitura}, ${pct(jogo.chance[jogo.maisProvavel])}. Não saiu.`;
    leitura.classList.add(jogo.acertouMaisProvavel ? "ok" : "erro");
  } else {
    leitura.textContent = `Leitura: ${nomeLeitura}, ${pct(jogo.chance[jogo.maisProvavel])}. Sem odd, sem palpite de aposta.`;
  }

  artigo.innerHTML = `
    <header><span>${jogo.quando ? quando(jogo.quando) : "Confronto restante"}</span>${resultado}</header>
    <div class="confronto">
      <div><b>${jogo.casaNome}</b><small>${jogo.golsEsperados.casa.toFixed(2).replace(".", ",")} gols</small></div>
      <div class="x">×</div>
      <div><b>${jogo.foraNome}</b><small>${jogo.golsEsperados.fora.toFixed(2).replace(".", ",")} gols</small></div>
    </div>
    <div class="barras">
      ${["casa", "empate", "fora"]
        .map((mercado) => {
          const classe = mercado === jogo.maisProvavel ? "destaque" : "";
          return `<div class="linha-mercado ${classe}"><span>${ROTULOS[mercado]}</span><div class="trilho"><i style="width:${pct(jogo.chance[mercado])}"></i></div><span>${pct(jogo.chance[mercado])}</span></div>`;
        })
        .join("")}
    </div>
    <div class="extra"><span>Ambos marcam ${pct(jogo.chance.ambos)}</span><span>Mais de 2,5 ${pct(jogo.chance.mais25)}</span></div>
    <ol class="placares">
      ${jogo.placares
        .map((placar) => `<li>${placar.casa}–${placar.fora} · ${pct(placar.chance)}</li>`)
        .join("")}
    </ol>`;
  artigo.append(leitura);
  return artigo;
}

function hero(resumo) {
  const bloco = document.createElement("section");
  bloco.className = "hero";
  bloco.innerHTML = `
    <p class="olho">Última rodada conferida antes do apito</p>
    <h2>A chance do jogo, não uma aposta</h2>
    <p>Em ${resumo.jogos} jogos de 2026, a leitura mais provável acertou ${pct(resumo.taxaMaisProvavel)}. O favorito da odd acertou ${pct(resumo.taxaFavorito)}. A regra de marcar vantagem sobre a odd foi desligada: ela perdeu dinheiro.</p>
    <div class="numeros">
      <div class="numero"><b>${pct(resumo.taxaMaisProvavel)}</b><span>acerto da leitura</span></div>
      <div class="numero"><b>${pct(resumo.taxaFavorito)}</b><span>acerto do favorito da odd</span></div>
    </div>`;
  return bloco;
}

async function paginaRodada() {
  miolo.replaceChildren(hero(inicio.resumo));
  const titulo = document.createElement("h2");
  titulo.textContent = "Última rodada";
  miolo.append(titulo);
  inicio.rodada.forEach((jogo) => miolo.append(cartao(jogo)));
}

async function paginaTimes() {
  const painelEl = document.createElement("section");
  painelEl.className = "painel";
  painelEl.innerHTML = `
    <h2>Confrontos que ainda faltam</h2>
    <p class="nota">${inicio.restantes} jogos do turno e returno ainda não aconteceram. A chance é de hoje. Não há odd futura nesta base, então não há palpite de aposta.</p>
    <label class="campo">Time<select id="escolha-time"></select></label>`;
  miolo.replaceChildren(painelEl);
  const select = painelEl.querySelector("select");
  times.forEach((time) => {
    const opcao = document.createElement("option");
    opcao.value = time.id;
    opcao.textContent = time.nome;
    select.append(opcao);
  });
  const lista = document.createElement("div");
  miolo.append(lista);
  const carregar = async () => {
    const resposta = await fetch(`/api/time/${encodeURIComponent(select.value)}`);
    const dados = await resposta.json();
    lista.replaceChildren();
    dados.jogos.forEach((jogo) => lista.append(cartao(jogo)));
  };
  select.addEventListener("change", carregar);
  await carregar();
}

async function paginaForca() {
  const resposta = await fetch("/api/forca");
  const dados = await resposta.json();
  const painelEl = document.createElement("section");
  painelEl.className = "painel";
  const linhas = dados.times
    .map((time) => {
      const ataque = time.ataque * 100;
      const defesa = time.defesa * 100;
      const classeAtaque = ataque >= 0 ? "pos" : "neg";
      const classeDefesa = defesa <= 0 ? "pos" : "neg";
      return `<tr><td>${time.nome}</td><td class="${classeAtaque}">${ataque >= 0 ? "+" : ""}${ataque.toFixed(0)}%</td><td class="${classeDefesa}">${defesa >= 0 ? "+" : ""}${defesa.toFixed(0)}%</td></tr>`;
    })
    .join("");
  painelEl.innerHTML = `
    <h2>Força no campeonato</h2>
    <p class="nota">Ataque é quanto o time marca a mais que a média. Defesa é quanto ele sofre a mais: número negativo é defesa boa. Mando de campo entra à parte, em todo jogo.</p>
    <table class="forca"><thead><tr><th>Time</th><th>Ataque</th><th>Defesa</th></tr></thead><tbody>${linhas}</tbody></table>`;
  miolo.replaceChildren(painelEl);
}

function paginaConta() {
  const resumo = inicio.resumo;
  const painelEl = document.createElement("section");
  painelEl.className = "painel";
  painelEl.innerHTML = `
    <h2>O que a conta fez em 2026</h2>
    <p class="nota">Cada jogo foi calculado só com o que já tinha acontecido. O modelo é o Dixon-Coles: gols de cada time, mando de campo e mais peso para o jogo recente. Todos os mercados saem da mesma tabela de placares.</p>
    <div class="numeros">
      <div class="numero"><b>${resumo.jogos}</b><span>jogos conferidos</span></div>
      <div class="numero"><b>${resumo.acertosMaisProvavel}</b><span>leituras certas no 1X2</span></div>
      <div class="numero"><b>${pct(resumo.taxaFavorito)}</b><span>favorito da odd</span></div>
      <div class="numero"><b>${dinheiro(resumo.lucroFavorito)}</b><span>seguir a odd, 1 unidade</span></div>
      <div class="numero"><b>${resumo.palpites}</b><span>vantagens marcadas</span></div>
      <div class="numero"><b>${dinheiro(resumo.lucroPalpite)}</b><span>seguir a vantagem</span></div>
    </div>
    <p class="nota">A vantagem era marcada quando a chance do modelo, na odd média, prometia mais de 3% de retorno. Ela acertou ${pct(resumo.taxaPalpite)} e perdeu dinheiro. A odd favorita também perde, porque a casa fica com a margem, mas perde menos. Por isso o site mostra a chance e não marca aposta.</p>
    <p class="nota">Um acerto passado não vale para o próximo jogo. Toda combinação continua incerta.</p>`;
  miolo.replaceChildren(painelEl);
}

const PAGINAS = {
  rodada: paginaRodada,
  times: paginaTimes,
  forca: paginaForca,
  conta: paginaConta,
};

async function abrir(nome) {
  pagina = nome;
  document.querySelectorAll(".menu button").forEach((botao) => {
    botao.classList.toggle("ativa", botao.dataset.pag === nome);
  });
  miolo.innerHTML = `<p class="vazio">Carregando...</p>`;
  await PAGINAS[nome]();
}

function liberar() {
  termo.hidden = true;
  site.hidden = false;
}

document.querySelectorAll("#form-termo input").forEach((caixa) => {
  caixa.addEventListener("change", () => {
    const marcadas = [...document.querySelectorAll("#form-termo input")].every((item) => item.checked);
    document.querySelector("#aceitar").disabled = !marcadas;
  });
});

document.querySelector("#form-termo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  localStorage.setItem(ACEITE, new Date().toISOString());
  liberar();
  await dadosProntos;
  abrir("rodada");
});

document.querySelectorAll(".menu button").forEach((botao) => {
  botao.addEventListener("click", () => abrir(botao.dataset.pag));
});

const dadosProntos = Promise.all([
  fetch("/api/inicio").then((resposta) => resposta.json()),
  fetch("/api/times").then((resposta) => resposta.json()).then((dados) => dados.times),
]).then(([painelInicial, listaTimes]) => {
  inicio = painelInicial;
  times = listaTimes;
});

async function comecar() {
  if (localStorage.getItem(ACEITE)) liberar();
  else termo.hidden = false;
  await dadosProntos;
  if (termo.hidden === false) return;
  abrir("rodada");
}

comecar();
