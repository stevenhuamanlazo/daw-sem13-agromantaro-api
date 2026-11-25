<#
  Pruebas manuales de la API desde PowerShell (Windows PowerShell 5.1 o PowerShell 7).
  Requiere la API levantada:  python manage.py runserver 8000
  Uso:  .\pruebas\pruebas_api.ps1
#>
$base = "http://localhost:8000"
function Titulo($t) { Write-Host "`n=== $t ===" -ForegroundColor Green }

Titulo "1) Raíz navegable (HATEOAS)"
Invoke-RestMethod "$base/api/" | ConvertTo-Json

Titulo "2) Filtros + orden + paginación"
$r = Invoke-RestMethod "$base/api/productos/?estado=activo&es_organico=true&precio_max=10&ordering=-creado&page=1&page_size=5"
"count=$($r.count)  páginas=$($r.total_paginas)  siguiente=$($r.next)"
$r.results | Select-Object nombre, precio, productor_nombre | Format-Table -AutoSize

Titulo "3) Producto destacado con enlaces HATEOAS"
(Invoke-RestMethod "$base/api/productos/destacados/")[0] | ConvertTo-Json -Depth 6

Titulo "4) CSRF + sesión (cookie en WebSession)"
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$token = (Invoke-RestMethod "$base/api/csrf/" -WebSession $s).csrfToken
$login = '{"username":"lucia","password":"Cliente123!"}'
Invoke-RestMethod "$base/api/sesion/" -Method Post -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRFToken" = $token } -Body $login | ConvertTo-Json
$token = (Invoke-RestMethod "$base/api/csrf/" -WebSession $s).csrfToken   # el login rota el token

Titulo "5) Crear pedido con cupón (CON token)"
$pedido = @{
  direccion_envio = "Jr. Real 450"; ciudad = "Huancayo"; cupon_codigo = "ANDES10"
  items = @(@{ producto = "$base/api/productos/quinua-roja/"; cantidad = 3 })
} | ConvertTo-Json -Depth 5
$creado = Invoke-RestMethod "$base/api/pedidos/" -Method Post -WebSession $s -ContentType "application/json" `
    -Headers @{ "X-CSRFToken" = $token } -Body $pedido
$creado | Select-Object codigo, estado, subtotal, descuento, costo_envio, total | Format-List

Titulo "6) El mismo POST SIN token debe fallar con 403"
try {
  Invoke-RestMethod "$base/api/pedidos/" -Method Post -WebSession $s -ContentType "application/json" -Body $pedido
} catch { "HTTP $([int]$_.Exception.Response.StatusCode) -> $($_.ErrorDetails.Message)" }

Titulo "7) Pagar el pedido siguiendo el enlace HATEOAS"
Invoke-RestMethod $creado._links.pagar.href -Method Post -WebSession $s -Headers @{ "X-CSRFToken" = $token } |
    Select-Object codigo, estado | Format-List

Titulo "8) Throttling: 25 lecturas anónimas seguidas (esperado 429 desde la #21)"
1..25 | ForEach-Object {
  try { $code = (Invoke-WebRequest "$base/api/categorias/" -UseBasicParsing).StatusCode }
  catch { $code = [int]$_.Exception.Response.StatusCode }
  "{0,2} -> {1}" -f $_, $code
}
