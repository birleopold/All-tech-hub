document.addEventListener('DOMContentLoaded', function () {
  var form = document.getElementById('document-form');
  var primarySave = document.getElementById('primary-save-button');
  var secondarySave = document.getElementById('secondary-save-button');

  if (!form || !primarySave || !secondarySave) {
    return;
  }

  if (document.getElementById('download-pdf-save-button')) {
    return;
  }

  var downloadButton = document.createElement('button');
  downloadButton.type = 'submit';
  downloadButton.name = 'save_action';
  downloadButton.value = 'pdf';
  downloadButton.id = 'download-pdf-save-button';
  downloadButton.className = 'btn btn-success';
  downloadButton.textContent = primarySave.textContent.indexOf('Create') !== -1
    ? 'Create and download PDF'
    : 'Save and download PDF';

  secondarySave.insertAdjacentElement('afterend', downloadButton);
});
