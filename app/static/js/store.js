document.addEventListener('DOMContentLoaded', () => {
  const cepInput = document.querySelector('[data-cep-input]');
  if (cepInput) {
    cepInput.addEventListener('input', () => {
      let v = cepInput.value.replace(/\D/g, '').slice(0, 8);
      if (v.length > 5) v = `${v.slice(0, 5)}-${v.slice(5)}`;
      cepInput.value = v;
    });
    cepInput.addEventListener('blur', async () => {
      const cep = cepInput.value.replace(/\D/g, '');
      if (cep.length !== 8) return;
      const status = document.querySelector('[data-cep-status]');
      if (status) status.textContent = 'Buscando endereço...';
      try {
        const res = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
        const data = await res.json();
        if (data.erro) throw new Error('CEP não encontrado');
        const fill = (selector, value) => {
          const el = document.querySelector(selector);
          if (el && !el.value) el.value = value || '';
        };
        fill('[name="customer_street"]', data.logradouro);
        fill('[name="customer_neighborhood"]', data.bairro);
        fill('[name="customer_city"]', data.localidade);
        fill('[name="customer_state"]', data.uf);
        const numberInput = document.querySelector('[name="customer_number"]');
        if (numberInput) numberInput.focus();
        if (status) status.textContent = 'Endereço preenchido automaticamente.';
      } catch (e) {
        if (status) status.textContent = 'Não foi possível localizar o CEP.';
      }
    });
  }

  const cpfInput = document.querySelector('[data-cpf-input]');
  if (cpfInput) {
    cpfInput.addEventListener('input', () => {
      let v = cpfInput.value.replace(/\D/g, '').slice(0, 11);
      v = v.replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d)/, '$1.$2').replace(/(\d{3})(\d{1,2})$/, '$1-$2');
      cpfInput.value = v;
    });
  }

  const fulfillment = document.querySelector('[name="fulfillment_type"]');
  const addressBlock = document.querySelector('[data-address-block]');
  const deliveryPreview = document.querySelector('[data-delivery-preview]');
  const deliveryValue = deliveryPreview?.dataset.deliveryFee || '0.00';
  const subtotalValue = deliveryPreview?.dataset.subtotal || '0.00';
  const totalValueEl = document.querySelector('[data-total-value]');

  function updateFulfillmentUI() {
    if (!fulfillment || !addressBlock) return;
    const isPickup = fulfillment.value === 'pickup';
    addressBlock.style.display = isPickup ? 'none' : 'grid';
    if (deliveryPreview) deliveryPreview.textContent = isPickup ? 'R$ 0,00' : `R$ ${deliveryValue.replace('.', ',')}`;
    if (totalValueEl) {
      const subtotal = Number(subtotalValue);
      const delivery = isPickup ? 0 : Number(deliveryValue);
      totalValueEl.textContent = `R$ ${(subtotal + delivery).toFixed(2).replace('.', ',')}`;
    }
  }
  if (fulfillment) {
    fulfillment.addEventListener('change', updateFulfillmentUI);
    updateFulfillmentUI();
  }

  document.querySelectorAll('[data-copy-text]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const text = btn.dataset.copyText;
      try {
        await navigator.clipboard.writeText(text);
        btn.innerHTML = '<i class="bi bi-check2"></i> Copiado';
      } catch {
        btn.textContent = 'Copie manualmente';
      }
    });
  });

  document.querySelectorAll('[data-category-chip]').forEach((chip) => {
    chip.addEventListener('click', () => {
      const target = document.querySelector(chip.dataset.categoryChip);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelectorAll('form').forEach((form) => {
    const qtyInput = form.querySelector('[data-qty-input]');
    const qtyValue = form.querySelector('[data-qty-value]');
    const minusBtn = form.querySelector('[data-qty-minus]');
    const plusBtn = form.querySelector('[data-qty-plus]');
    if (!qtyInput || !qtyValue || !minusBtn || !plusBtn) return;
    const sync = () => {
      const qty = Math.max(1, Number(qtyInput.value || 1));
      qtyInput.value = qty;
      qtyValue.textContent = qty;
      minusBtn.disabled = qty <= 1;
    };
    minusBtn.addEventListener('click', () => { qtyInput.value = Math.max(1, Number(qtyInput.value || 1) - 1); sync(); });
    plusBtn.addEventListener('click', () => { qtyInput.value = Number(qtyInput.value || 1) + 1; sync(); });
    sync();
  });

  const orderRoot = document.querySelector('[data-order-token][data-store-slug]');
  function storeTokens(slug, token) {
    if (!slug || !token) return;
    const key = `delivery_orders_${slug}`;
    const current = JSON.parse(localStorage.getItem(key) || '[]').filter(Boolean);
    if (!current.includes(token)) current.unshift(token);
    localStorage.setItem(key, JSON.stringify(current.slice(0, 20)));
  }
  function getTokens(slug) {
    try { return JSON.parse(localStorage.getItem(`delivery_orders_${slug}`) || '[]'); } catch { return []; }
  }
  if (orderRoot) storeTokens(orderRoot.dataset.storeSlug, orderRoot.dataset.orderToken);

  document.querySelectorAll('[data-orders-link][data-store-slug]').forEach((link) => {
    const slug = link.dataset.storeSlug;
    const tokens = getTokens(slug);
    if (!tokens.length) return;
    const url = new URL(link.href, window.location.origin);
    tokens.forEach((token) => url.searchParams.append('t', token));
    link.href = url.pathname + url.search;
  });

  const ordersPage = document.querySelector('[data-orders-page][data-store-slug]');
  if (ordersPage) {
    const slug = ordersPage.dataset.storeSlug;
    const tokens = getTokens(slug);
    const url = new URL(window.location.href);
    if (!url.searchParams.getAll('t').length && tokens.length) {
      tokens.forEach((token) => url.searchParams.append('t', token));
      window.location.replace(url.pathname + url.search);
    }
  }
});
