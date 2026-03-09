document.addEventListener('DOMContentLoaded', () => {
  const cepInput = document.querySelector('[data-cep-input]');
  if (cepInput) {
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
    if (deliveryPreview) {
      deliveryPreview.textContent = isPickup ? 'R$ 0,00' : `R$ ${deliveryValue.replace('.', ',')}`;
    }
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
});
