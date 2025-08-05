// static/js/app.js
document.addEventListener('DOMContentLoaded', function() {
    const cameraRadio  = document.getElementById('optCamera');
    const libraryRadio = document.getElementById('optLibrary');
    const fileInput    = document.getElementById('imageInput');
  
    function updateCapture() {
      if (cameraRadio.checked) {
        // カメラで撮影
        fileInput.setAttribute('capture', 'environment');
      } else {
        // ライブラリから選択
        fileInput.removeAttribute('capture');
      }
    }
  
    cameraRadio.addEventListener('change', updateCapture);
    libraryRadio.addEventListener('change', updateCapture);
    updateCapture();
  });
  