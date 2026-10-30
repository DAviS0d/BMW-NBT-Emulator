precision lowp float;

varying mediump vec2 vTexCoord;
varying vec4 vColor;

uniform sampler2D tex0; 
uniform vec2 u_userRepeatTexture;

void main()
{
    vec2 texCoord = vec2(vTexCoord.x - u_userRepeatTexture.x*floor(vTexCoord.x), 
        vTexCoord.y - u_userRepeatTexture.y*floor(vTexCoord.y));
    vec4 texColor = texture2D(tex0, texCoord);
    gl_FragColor.rgb = texColor.rgb * vColor.rgb;
    gl_FragColor.a = texColor.r;
}