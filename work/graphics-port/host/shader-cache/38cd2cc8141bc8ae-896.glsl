precision mediump float;

varying mediump vec2 vTexCoord;
uniform sampler2D tex0;
uniform sampler2D tex1;
uniform float posY;

vec4 result;

void main()
{		
	vec4 texColor = texture2D(tex0, vTexCoord.xy + vec2(0.0, - posY+0.02)); //add 2percent to posY cause the lines are not positioned at images bottom because of the lower fade 
	vec4 maskcolor = texture2D(tex1, vTexCoord.xy);	
	gl_FragColor = texColor * maskcolor.r;	
	
	if(posY>0.7)
	{
		float alpha = 3.33 * (1.0 - posY); //if 70% of the vertical image coords are rendered, calculate an alpha ...
		gl_FragColor.a = texColor.a * alpha * maskcolor.r; //... which maps the remaining 30% of the vertical texture coords to an alpha value between 1 and 0 to fade the tope line
	}
}
