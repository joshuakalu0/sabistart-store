// Professional Settings Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    initializeToggles();
    initializeFormValidation();
    initializeAjaxSubmission();
    initializePhoneInput();
});

/**
 * Initialize toggle switches
 */
function initializeToggles() {
    const toggles = document.querySelectorAll('.toggle-switch-wrapper input[type="checkbox"]');

    toggles.forEach(toggle => {
        toggle.addEventListener('change', function() {
            // Add visual feedback
            const wrapper = this.closest('.toggle-switch-wrapper');
            wrapper.classList.add('toggling');

            setTimeout(() => {
                wrapper.classList.remove('toggling');
            }, 300);

            // If this is maintenance mode, show confirmation
            if (this.id.includes('maintenance')) {
                handleMaintenanceToggle(this);
            }
        });
    });
}

/**
 * Handle maintenance mode toggle
 */
function handleMaintenanceToggle(toggle) {
    const isEnabled = toggle.checked;
    const message = isEnabled
        ? 'Maintenance mode will temporarily disable your store. Continue?'
        : 'Disable maintenance mode and make your store accessible?';

    if (confirm(message)) {
        // You can add AJAX call here to toggle immediately
        console.log('Maintenance mode:', isEnabled);
    } else {
        toggle.checked = !isEnabled;
    }
}

/**
 * Initialize form validation
 */
function initializeFormValidation() {
    const forms = document.querySelectorAll('.settings-form');

    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, select, textarea');

        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                validateField(this);
            });

            input.addEventListener('input', function() {
                // Clear error on input
                const errorDiv = this.parentElement.querySelector('.field-error');
                if (errorDiv) {
                    errorDiv.remove();
                }
                this.classList.remove('is-invalid');
            });
        });
    });
}

/**
 * Validate individual field
 */
function validateField(field) {
    const value = field.value.trim();
    const isRequired = field.hasAttribute('required') ||
                      field.parentElement.querySelector('.required');

    // Remove existing error
    const existingError = field.parentElement.querySelector('.field-error');
    if (existingError) {
        existingError.remove();
    }
    field.classList.remove('is-invalid');

    // Check if required field is empty
    if (isRequired && !value) {
        showFieldError(field, 'This field is required');
        return false;
    }

    // Email validation
    if (field.type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            showFieldError(field, 'Please enter a valid email address');
            return false;
        }
    }

    // Phone validation
    if (field.name === 'phone' && value) {
        const phoneRegex = /^[\d\s\+\-\(\)]+$/;
        if (!phoneRegex.test(value)) {
            showFieldError(field, 'Please enter a valid phone number');
            return false;
        }
    }

    // URL validation
    if (field.type === 'url' && value) {
        try {
            new URL(value);
        } catch {
            showFieldError(field, 'Please enter a valid URL');
            return false;
        }
    }

    // Number validation
    if (field.type === 'number' && value) {
        const min = field.getAttribute('min');
        const max = field.getAttribute('max');
        const numValue = parseFloat(value);

        if (min && numValue < parseFloat(min)) {
            showFieldError(field, `Value must be at least ${min}`);
            return false;
        }

        if (max && numValue > parseFloat(max)) {
            showFieldError(field, `Value must not exceed ${max}`);
            return false;
        }
    }

    return true;
}

/**
 * Show field error
 */
function showFieldError(field, message) {
    field.classList.add('is-invalid');

    const errorDiv = document.createElement('div');
    errorDiv.className = 'field-error';
    errorDiv.textContent = message;

    field.parentElement.appendChild(errorDiv);
}

/**
 * Initialize AJAX form submission
 */
function initializeAjaxSubmission() {
    const forms = document.querySelectorAll('.settings-form');

    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Validate all fields before submission
            let isValid = true;
            const inputs = form.querySelectorAll('input:not([type="hidden"]), select, textarea');

            inputs.forEach(input => {
                if (!validateField(input)) {
                    isValid = false;
                }
            });

            if (!isValid) {
                e.preventDefault();
                showNotification('Please correct the errors before saving', 'error');
                return;
            }

            // Add loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                const originalText = submitBtn.innerHTML;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';

                // Restore button after form submission
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = originalText;
                }, 3000);
            }
        });
    });
}

/**
 * Initialize phone input with country code
 */
function initializePhoneInput() {
    const countryCodeSelect = document.getElementById('countryCode');
    const phoneInput = document.querySelector('input[name="phone"]');

    if (countryCodeSelect && phoneInput) {
        countryCodeSelect.addEventListener('change', function() {
            // Update phone input placeholder
            const code = this.value;
            phoneInput.placeholder = `${code} 1234567890`;
        });
    }
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        ${message}
    `;

    const content = document.querySelector('.settings-content');
    content.insertBefore(notification, content.firstChild);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Initialize map (placeholder for future implementation)
 */
function initializeMap() {
    // This would integrate with Google Maps or similar
    console.log('Map initialization placeholder');
}

/**
 * Handle fullscreen map
 */
function toggleMapFullscreen() {
    const mapContainer = document.querySelector('.map-container');
    if (!document.fullscreenElement) {
        mapContainer.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

/**
 * Auto-save functionality (optional)
 */
function enableAutoSave(formId, interval = 30000) {
    const form = document.getElementById(formId);
    if (!form) return;

    let autoSaveTimer;
    const inputs = form.querySelectorAll('input, select, textarea');

    inputs.forEach(input => {
        input.addEventListener('change', function() {
            clearTimeout(autoSaveTimer);
            autoSaveTimer = setTimeout(() => {
                saveFormData(form);
            }, interval);
        });
    });
}

/**
 * Save form data via AJAX
 */
function saveFormData(form) {
    const formData = new FormData(form);

    fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showNotification('Settings saved automatically', 'success');
        }
    })
    .catch(error => {
        console.error('Auto-save failed:', error);
    });
}

/**
 * Copy to clipboard
 */
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard', 'success');
    });
}

/**
 * Confirm before leaving with unsaved changes
 */
window.addEventListener('beforeunload', function(e) {
    const forms = document.querySelectorAll('.settings-form');
    let hasChanges = false;

    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            if (input.dataset.originalValue !== input.value) {
                hasChanges = true;
            }
        });
    });

    if (hasChanges) {
        e.preventDefault();
        e.returnValue = '';
    }
});

/**
 * Store original values on page load
 */
window.addEventListener('load', function() {
    const inputs = document.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.dataset.originalValue = input.value;
    });
});
