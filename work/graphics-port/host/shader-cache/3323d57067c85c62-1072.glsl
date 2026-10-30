precision mediump float;

varying vec2 vTexCoord;
varying vec4 vColor;

uniform sampler2D tex0; 
uniform int u_useTexture;
uniform int u_useRedChannelAsAlpha;
uniform vec2 u_userRepeatTexture;

void main()
{
    float useTexture = float(u_useTexture);
    vec2 texCoord = vec2(vTexCoord.x - u_userRepeatTexture.x*floor(vTexCoord.x), 
        vTexCoord.y - u_userRepeatTexture.y*floor(vTexCoord.y));
    vec4 texColor = texture2D(tex0, texCoord);
    gl_FragColor = (texColor*useTexture) * vColor + (1.-useTexture)*vColor;
    float useRedChannel = float(u_useRedChannelAsAlpha);
    gl_FragColor.a = (gl_FragColor.a*(1.-useRedChannel)) + texColor.r*vColor.a*useRedChannel;
}