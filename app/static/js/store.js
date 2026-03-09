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

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-qty-stepper]').forEach((stepper) => {
    const input = stepper.querySelector('[data-qty-input]');
    const display = stepper.querySelector('[data-qty-display]');
    const setQty = (value) => {
      const qty = Math.max(1, Number(value) || 1);
      if (input) input.value = qty;
      if (display) display.value = qty;
    };
    setQty(input?.value || 1);
    stepper.querySelectorAll('[data-qty-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const current = Number(input?.value || display?.value || 1);
        setQty(current + (btn.dataset.qtyAction === 'plus' ? 1 : -1));
      });
    });
  });
});


document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-toggle-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const form = document.querySelector(btn.dataset.toggleEdit);
      if (!form) return;
      const hidden = form.hasAttribute('hidden');
      if (hidden) {
        form.removeAttribute('hidden');
        btn.textContent = 'Fechar';
      } else {
        form.setAttribute('hidden', '');
        btn.textContent = 'Editar';
      }
    });
  });

  document.querySelectorAll('[data-favorite-store]').forEach((btn) => {
    const key = `favorite-store:${btn.dataset.favoriteStore}`;
    const icon = btn.querySelector('i');
    const renderFavorite = () => {
      const active = localStorage.getItem(key) === '1';
      btn.classList.toggle('is-favorite', active);
      if (icon) {
        icon.className = active ? 'bi bi-heart-fill' : 'bi bi-heart';
      }
    };
    renderFavorite();
    btn.addEventListener('click', () => {
      const active = localStorage.getItem(key) === '1';
      localStorage.setItem(key, active ? '0' : '1');
      renderFavorite();
    });
  });

  document.querySelectorAll('[data-share-store]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const url = btn.dataset.shareUrl || window.location.href;
      const title = btn.dataset.shareTitle || document.title;
      try {
        if (navigator.share) {
          await navigator.share({ title, text: `Olha essa loja: ${title}`, url });
          return;
        }
      } catch (err) {}
      const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(`Olha essa loja: ${title} ${url}`)}`;
      window.open(whatsappUrl, '_blank', 'noopener');
    });
  });
});
