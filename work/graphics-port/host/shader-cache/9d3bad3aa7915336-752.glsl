precision mediump float;

varying vec2 vTexCoord;
varying vec4 vColor;

uniform sampler2D tex0; 
uniform vec2 u_userRepeatTexture;

void main()
{
    vec2 texCoord = vec2(vTexCoord.x - u_userRepeatTexture.x*floor(vTexCoord.x), 
                         vTexCoord.y - u_userRepeatTexture.y*floor(vTexCoord.y));
    gl_FragColor = texture2D(tex0, texCoord);
}